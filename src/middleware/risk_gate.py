"""Jev-scored tool-risk gate in front of the human-in-the-loop interrupt.

`HumanInTheLoopMiddleware` interrupts a tool call when its `when` predicate returns True.
That predicate is where the risk assessment lives, and it combines two signals:

- the deterministic policy check (`evaluate_refund`), which knows the dollar thresholds;
- a Jev `Score` over the proposed call *and the conversation that led to it*, which
  catches a technically-in-limits refund the customer never actually justified.

Either one firing sends the call to a human.
"""

from __future__ import annotations

import sys

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
    ToolCallRequest,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolCall

from src.classification.jev import score_tool_risk
from src.config import (
    REFUND_AUTO_MAX,
    TOOL_RISK_REVIEW_MIN,
    VOUCHER_DEFAULT_AMOUNT,
    VOUCHER_MAX_AMOUNT,
)
from src.policy import evaluate_cancellation, evaluate_refund
from src.trace import HITL_REQUEST, JEV_RISK, record, record_once, turn_of

_TRANSCRIPT_TURNS = 8
"""How much recent conversation the risk classifier gets to see."""


def _transcript(state) -> str:  # noqa: ANN001 - state shape varies by caller
    messages = state.get("messages", []) if isinstance(state, dict) else []
    lines: list[str] = []
    for message in messages[-_TRANSCRIPT_TURNS:]:
        if isinstance(message, HumanMessage):
            role = "customer"
        elif isinstance(message, AIMessage):
            role = "agent"
        else:
            continue
        text = message.text if hasattr(message, "text") else str(message.content)
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def needs_human_review(request: ToolCallRequest) -> bool:
    """Decide whether this refund call has to pause for a human."""
    args = request.tool_call["args"]
    try:
        amount = float(args.get("amount"))
    except (TypeError, ValueError):
        # Malformed call; let RefundPolicyMiddleware reject it with a useful message.
        return False

    customer_id = request.runtime.context.customer_id
    decision = evaluate_refund(customer_id=customer_id, amount=amount)

    if decision.verdict == "deny":
        # Policy will refuse it outright. Do not waste a reviewer's time.
        return False

    if decision.verdict == "review":
        print(
            f"  [risk gate] review required — {decision.reason}",
            file=sys.stderr,
        )
        record_once(
            HITL_REQUEST,
            f"Refund ${amount:.2f} paused for approval — {decision.reason}",
            {"tool": "issue_refund", "args": args, "trigger": "policy threshold",
             "reason": decision.reason, "auto_limit": REFUND_AUTO_MAX},
            customer_id=customer_id, turn=turn_of(request.state),
            dedupe_key=f"issue_refund:{amount}",
        )
        return True

    risk = score_tool_risk(
        tool_name=request.tool_call["name"],
        args=args,
        conversation=_transcript(request.state),
    )
    escalate = risk >= TOOL_RISK_REVIEW_MIN
    print(
        f"  [risk gate] Jev risk {risk:.2f}/2 — "
        f"{'review required' if escalate else 'auto-approved'}",
        file=sys.stderr,
    )
    record(
        JEV_RISK,
        f"Jev scored this refund {risk:.2f}/2 — "
        f"{'needs a human' if escalate else 'safe to run'}",
        {
            "tool": request.tool_call["name"],
            "args": args,
            "risk_score": risk,
            "threshold": TOOL_RISK_REVIEW_MIN,
            "needs_review": escalate,
            "question": "Score 0-2 — how risky is letting this action run unsupervised, "
                        "judging only by what the conversation established?",
            "rubric": ["Routine", "Notable", "Severe"],
        },
        customer_id=customer_id, turn=turn_of(request.state),
    )
    if escalate:
        record_once(
            HITL_REQUEST,
            f"Refund ${amount:.2f} paused for approval — Jev risk {risk:.2f}/2",
            {"tool": "issue_refund", "args": args, "trigger": "jev risk score",
             "risk_score": risk},
            customer_id=customer_id, turn=turn_of(request.state),
            dedupe_key=f"issue_refund:{amount}",
        )
    return escalate


def describe_refund(tool_call: ToolCall, state, runtime) -> str:  # noqa: ANN001
    """What the human reviewer reads before deciding."""
    args = tool_call["args"]
    amount = args.get("amount")
    customer_id = getattr(runtime.context, "customer_id", "unknown")

    try:
        decision = evaluate_refund(customer_id=customer_id, amount=float(amount))
        history = (
            f"{decision.recent_refund_count} refunds in the policy window, "
            f"{decision.refund_rate:.0%} of orders refunded"
        )
        verdict = decision.reason
    except (TypeError, ValueError):
        history = "unavailable"
        verdict = "amount could not be parsed"

    return (
        f"Refund ${amount} on order {args.get('order_id')} for {customer_id}\n"
        f"Reason given: {args.get('reason')}\n"
        f"Customer history: {history}\n"
        f"Why this stopped: {verdict}\n"
        f"Auto-approval limit: ${REFUND_AUTO_MAX:.2f}"
    )


def describe_voucher(tool_call: ToolCall, state, runtime) -> str:  # noqa: ANN001
    """What the reviewer reads when deciding a goodwill remedy."""
    args = tool_call["args"]
    order_id = args.get("order_id")
    customer_id = getattr(runtime.context, "customer_id", "unknown")

    context_line = "Order context unavailable."
    if order_id:
        decision = evaluate_cancellation(customer_id=customer_id, order_id=str(order_id))
        context_line = (
            f"Order {order_id}: stage={decision.stage}, total=${decision.order_total:.2f}. "
            f"{decision.reason}"
        )

    history = (state or {}).get("frustration_history") or []
    trend = " -> ".join(f"{f:.2f}" for f in history) if history else "n/a"

    record_once(
        HITL_REQUEST,
        f"Voucher ${args.get('amount', VOUCHER_DEFAULT_AMOUNT)} paused for approval",
        {"tool": "issue_voucher", "args": args, "trigger": "vouchers always review",
         "frustration_history": history, "ceiling": VOUCHER_MAX_AMOUNT},
        customer_id=customer_id, turn=len(history),
        dedupe_key=f"issue_voucher:{args.get('amount')}:{args.get('order_id')}",
    )

    return (
        f"Goodwill voucher for {customer_id}\n"
        f"{context_line}\n"
        f"Proposed: ${args.get('amount', VOUCHER_DEFAULT_AMOUNT)} valid "
        f"{args.get('valid_days')} days\n"
        f"Reason: {args.get('reason')}\n"
        f"Customer frustration across turns (0=calm, 2=angry): {trend}\n"
        f"Voucher ceiling: ${VOUCHER_MAX_AMOUNT:.2f}. Reject to decline the remedy."
    )


def build_risk_gate() -> HumanInTheLoopMiddleware:
    """Human approval for refunds the risk gate flags, and for every voucher."""
    return HumanInTheLoopMiddleware(
        interrupt_on={
            "issue_voucher": InterruptOnConfig(
                allowed_decisions=["approve", "edit", "reject"],
                description=describe_voucher,
                args_schema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "amount": {"type": "number"},
                        "valid_days": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["reason"],
                },
            ),
            "issue_refund": InterruptOnConfig(
                allowed_decisions=["approve", "edit", "reject"],
                description=describe_refund,
                when=needs_human_review,
                args_schema={
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                        "amount": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["order_id", "amount", "reason"],
                },
            )
        },
        description_prefix="Needs approval",
    )
