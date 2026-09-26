"""Jev triage: one classification pass per customer turn.

Runs as `before_model`, but only when the newest message actually came from the customer.
Tool-loop iterations reuse the classification already in state, so a single customer turn
costs exactly one Jev call no matter how many tools the agent ends up using.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from src.classification.jev import Triage, classify_message
from src.config import (
    ESCALATE_FRUSTRATION,
    FRUSTRATION_RISE_FOR_CANCEL,
    FRUSTRATION_TURNS_FOR_CANCEL,
)
from src.context import SupportContext
from src.middleware.state import SupportState
from src.policy import cancellable_stuck_order
from src.trace import (
    ESCALATION_RULE,
    JEV_TRIAGE,
    USER_MESSAGE,
    record,
    turn_of,
)


class JevTriageMiddleware(AgentMiddleware[SupportState, SupportContext]):
    """Classify the customer's message and decide whether the thread must be escalated."""

    state_schema = SupportState

    def before_model(
        self, state: SupportState, runtime: Runtime[SupportContext]
    ) -> dict[str, Any] | None:
        messages = state["messages"]
        if not messages or not isinstance(messages[-1], HumanMessage):
            # Mid tool-loop: the existing triage still describes this turn.
            return None

        text = _as_text(messages[-1].content)
        customer_id = runtime.context.customer_id
        turn = int(state.get("turn", 0)) + 1

        record(
            USER_MESSAGE, text, {"text": text},
            customer_id=customer_id, turn=turn,
        )

        triage = classify_message(text)

        record(
            JEV_TRIAGE,
            f"{triage.category} ({triage.category_confidence:.0%} confident) · "
            f"urgency {triage.urgency:.2f} · frustration {triage.frustration:.2f}/2",
            {
                "category": triage.category,
                "category_confidence": triage.category_confidence,
                "urgency": triage.urgency,
                "frustration": triage.frustration,
                "needs_reasoning": triage.needs_reasoning,
                "is_urgent": triage.is_urgent,
                "is_upset": triage.is_upset,
                "questions": {
                    "category": "Choice — which support workflow handles this?",
                    "urgency": "Noul — does this need attention right now?",
                    "frustration": "Score 0-2 — how frustrated does the customer sound?",
                    "needs_reasoning": "Noul — does answering need policy judgment?",
                },
            },
            customer_id=customer_id, turn=turn,
        )

        history = [*state.get("frustration_history", []), triage.frustration]
        upset_turns = sum(1 for f in history if f >= ESCALATE_FRUSTRATION)
        sustained, why_sustained = _frustration_building(history, upset_turns)

        update: dict[str, Any] = {
            "turn": turn,
            "triage": triage.to_state(),
            "frustration_history": history,
            "frustration_sustained": sustained,
            "cancel_unlocked_order": "",
            "escalation_required": False,
            "escalation_note": "",
        }

        unlocked = cancellable_stuck_order(runtime.context.customer_id) if sustained else ""
        if unlocked:
            update["cancel_unlocked_order"] = unlocked

        note = _escalation_note(triage, runtime.context.customer_id)
        if not note and sustained and not unlocked:
            # Frustration kept building and there is nothing left to try: every remedy
            # this agent has either ran already or is refused for this order's stage.
            # When there *is* something left -- `unlocked` -- the agent settles it
            # instead, and no human is pulled in for work the agent can finish.
            note = (
                f"{why_sustained} Whatever has been offered has not landed, and nothing "
                f"left in the agent's tools will fix it."
            )
        record(
            ESCALATION_RULE,
            note or "No escalation rule fired",
            {
                "escalated": bool(note),
                "note": note,
                "frustration_history": history,
                "upset_turns": upset_turns,
                "frustration_sustained": sustained,
                "why_sustained": why_sustained,
                "cancel_unlocked_order": update.get("cancel_unlocked_order") or None,
            },
            customer_id=customer_id, turn=turn,
        )

        if note:
            update["escalation_required"] = True
            update["escalation_note"] = note

        return update


def _frustration_building(history: list[float], upset_turns: int) -> tuple[bool, str]:
    """Has this customer's frustration kept building, rather than merely spiked once?

    Two ways to qualify: they have been upset across several turns, or they crossed the
    upset line on this turn having climbed to get there.
    """
    if upset_turns >= FRUSTRATION_TURNS_FOR_CANCEL:
        return True, (
            f"The customer has been upset across {upset_turns} turns "
            f"(now {history[-1]:.2f}/2)."
        )

    if len(history) >= 2:
        current, previous = history[-1], history[-2]
        if (
            current >= ESCALATE_FRUSTRATION
            and current - previous >= FRUSTRATION_RISE_FOR_CANCEL
        ):
            return True, (
                f"The customer's frustration is still climbing "
                f"({previous:.2f} -> {current:.2f} out of 2)."
            )

    return False, ""


def _escalation_note(triage: Triage, customer_id: str) -> str:
    """Return the reason this thread must be escalated, or an empty string.

    The headline rule: a human is for what the agent *cannot* do, not for what it would
    rather not do. Asking for a person, and legal or safety matters, are the two things
    no amount of tooling settles, so they go straight over.

    Being upset about a late order is not one of them. That case has a remedy the agent
    can run -- say what actually happened, put in a voucher, and cancel once the stage
    ladder allows it -- and routing it to a human anyway costs the customer a wait for an
    answer the agent already had. An earlier version escalated every upset customer with
    an order past `ESCALATE_LATE_MINUTES`, which is most unhappy customers on a bad day,
    and it is why so little was contained. Frustration that keeps building *after* the
    remedy still escalates: see `_frustration_building`, and the `unlocked` branch in
    `before_model`, which prefers settling to handing over.
    """
    if triage.category == "escalation":
        return "The customer is asking for a human, or raising a legal or safety matter."

    return ""


def _as_text(content: Any) -> str:
    """Flatten message content, which may be a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return str(content)
