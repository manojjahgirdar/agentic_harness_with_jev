"""Money-movement policy enforcement: refunds and cancellations.

This is the last line before money moves. The human-in-the-loop gate (see
`risk_gate.py`) can pause a refund for approval, but a reviewer approving something is
not the same as policy allowing it: a customer who has tripped the abuse thresholds is
refused here regardless, and the model is told to escalate instead of retrying.

Both this middleware and the risk gate call `policy.evaluate_refund`, so there is exactly
one definition of the rules.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.config import (
    REFUND_AUTO_MAX,
    REFUND_HARD_MAX,
    VOUCHER_DEFAULT_AMOUNT,
    VOUCHER_MAX_AMOUNT,
)
from src.context import SupportContext
from src.middleware.state import SupportState
from src.policy import evaluate_cancellation, evaluate_refund, existing_voucher
from src.trace import POLICY, record, turn_of


class RefundPolicyMiddleware(AgentMiddleware[SupportState, SupportContext]):
    """Refuse money movements that policy forbids; let the permitted ones through."""

    state_schema = SupportState

    def __init__(self, *, verbose: bool = True) -> None:
        self.verbose = verbose

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        name = request.tool_call["name"]
        if name == "cancel_order":
            return self._guard_cancellation(request, handler)
        if name == "issue_voucher":
            return self._guard_voucher(request, handler)
        if name != "issue_refund":
            return handler(request)

        args = request.tool_call["args"]
        amount = _as_float(args.get("amount"))
        customer_id = request.runtime.context.customer_id

        if amount is None:
            return ToolMessage(
                content=(
                    "Refused: `amount` must be a number in dollars. Nothing was refunded."
                ),
                name="issue_refund",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

        decision = evaluate_refund(customer_id=customer_id, amount=amount)

        if self.verbose:
            print(
                f"  [refund policy] {decision.verdict} — {decision.reason}",
                file=sys.stderr,
            )

        record(
            POLICY,
            f"issue_refund — {decision.verdict}: {decision.reason}",
            {
                "tool": "issue_refund",
                "verdict": decision.verdict,
                "reason": decision.reason,
                "amount": decision.amount,
                "recent_refund_count": decision.recent_refund_count,
                "refund_rate": decision.refund_rate,
                "abusive": decision.abusive,
                "auto_limit": REFUND_AUTO_MAX,
                "hard_ceiling": REFUND_HARD_MAX,
            },
            customer_id=request.runtime.context.customer_id,
            turn=turn_of(request.state),
        )

        if decision.verdict == "deny":
            return ToolMessage(
                content=(
                    f"REFUND REFUSED BY POLICY. {decision.reason}\n\n"
                    "Do not retry this refund at a lower amount and do not explain the "
                    "policy to the customer. Call `escalate_to_human` so a specialist can "
                    "review the account, and tell the customer their request is with a "
                    "specialist."
                ),
                name="issue_refund",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

        return handler(request)

    def _guard_cancellation(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Apply the fulfilment-stage ladder before an order can be cancelled."""
        order_id = request.tool_call["args"].get("order_id", "")
        state = request.state if isinstance(request.state, dict) else {}
        decision = evaluate_cancellation(
            customer_id=request.runtime.context.customer_id,
            order_id=str(order_id),
            frustration_sustained=bool(state.get("frustration_sustained")),
        )

        if self.verbose:
            print(
                f"  [cancel policy] {decision.verdict} — {decision.reason}",
                file=sys.stderr,
            )

        record(
            POLICY,
            f"cancel_order — {decision.verdict}: {decision.reason}",
            {
                "tool": "cancel_order",
                "verdict": decision.verdict,
                "reason": decision.reason,
                "stage": decision.stage,
                "order_total": decision.order_total,
                "refund_amount": decision.refund_amount,
                "remedy_first": decision.remedy_first,
                "frustration_sustained": bool(state.get("frustration_sustained")),
            },
            customer_id=request.runtime.context.customer_id,
            turn=turn_of(request.state),
        )

        if decision.verdict == "deny":
            if decision.remedy_first:
                nudge = (
                    "Offer a goodwill voucher with `issue_voucher` instead. Tell the "
                    "customer the food is made and waiting on a courier, say what you are "
                    "offering, and do not mention cancelling as an option yet."
                )
            elif decision.stage == "with_courier":
                nudge = (
                    "Do not retry and do not offer a refund. The delivery is still coming. "
                    "Offer a goodwill voucher with `issue_voucher` for the delay, or call "
                    "`escalate_to_human` if the customer will not accept that."
                )
            else:
                nudge = (
                    "Do not retry. If the customer is still owed something, work out what "
                    "actually went wrong and use `issue_refund`, or call "
                    "`escalate_to_human` if you cannot resolve it."
                )
            return ToolMessage(
                content=f"CANCELLATION REFUSED. {decision.reason}\n\n{nudge}",
                name="cancel_order",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

        return handler(request)

    def _guard_voucher(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        """Cap voucher value. A reviewer may raise it, but not without limit."""
        args = request.tool_call["args"]
        amount = _as_float(args.get("amount", VOUCHER_DEFAULT_AMOUNT))

        already = existing_voucher(
            request.runtime.context.customer_id, args.get("order_id")
        )
        if already:
            if self.verbose:
                print(
                    f"  [voucher policy] deny — {already['code']} already issued",
                    file=sys.stderr,
                )
            record(
                POLICY,
                f"issue_voucher — deny: {already['code']} already issued on this order",
                {"tool": "issue_voucher", "verdict": "deny",
                 "reason": "one voucher per order", "existing": already},
                customer_id=request.runtime.context.customer_id,
                turn=turn_of(request.state),
            )
            return ToolMessage(
                content=(
                    f"VOUCHER REFUSED. Voucher {already['code']} for "
                    f"${already['amount']:.2f} was already issued on this order. Do not "
                    f"offer the same remedy twice -- it reads as stalling. If that is no "
                    f"longer enough, escalate with `escalate_to_human`, or cancel the "
                    f"order if the policy layer now permits it."
                ),
                name="issue_voucher",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

        if amount is None or amount <= 0:
            return ToolMessage(
                content="Refused: voucher `amount` must be a positive number of dollars.",
                name="issue_voucher",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

        if amount > VOUCHER_MAX_AMOUNT:
            return ToolMessage(
                content=(
                    f"VOUCHER REFUSED. ${amount:.2f} is above the "
                    f"${VOUCHER_MAX_AMOUNT:.2f} voucher ceiling. Re-issue at or below the "
                    f"ceiling, or call `escalate_to_human` if that is not enough."
                ),
                name="issue_voucher",
                tool_call_id=request.tool_call["id"],
                status="error",
            )

        if self.verbose:
            print(f"  [voucher policy] allow — ${amount:.2f}", file=sys.stderr)

        record(
            POLICY,
            f"issue_voucher — allow: ${amount:.2f} (human approval still required)",
            {"tool": "issue_voucher", "verdict": "allow", "amount": amount,
             "ceiling": VOUCHER_MAX_AMOUNT,
             "reason": "within the voucher ceiling; always goes to a reviewer"},
            customer_id=request.runtime.context.customer_id,
            turn=turn_of(request.state),
        )
        return handler(request)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
