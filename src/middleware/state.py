"""State schema shared by the support middleware.

`create_agent` merges the `state_schema` of every middleware, so declaring these keys on
the triage middleware is enough to make them readable everywhere downstream.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentState
from typing_extensions import NotRequired


class SupportState(AgentState):
    """Agent state plus whatever Jev and the policy checks worked out this turn."""

    turn: NotRequired[int]
    """Which customer turn this is, counted explicitly.

    Deriving it from the transcript breaks the moment `SummarizationMiddleware` compacts
    old messages away -- the HumanMessages it counted are gone, and later events in the
    same turn get filed under an earlier one.
    """

    triage: NotRequired[dict[str, Any]]
    """Serialized `Triage` for the most recent user message."""

    escalation_required: NotRequired[bool]
    """Set when the upset-customer / badly-late-order rule fires."""

    escalation_note: NotRequired[str]
    """Human-readable reason for `escalation_required`, injected into the prompt."""

    frustration_history: NotRequired[list[float]]
    """Frustration score for every customer turn in this thread, oldest first.

    Persisted with the checkpoint, so "is this customer getting angrier" survives the
    process exiting and is answerable on turn one of a resumed conversation.
    """

    frustration_sustained: NotRequired[bool]
    """True once the customer's frustration is sustained or still climbing.

    This is the flag that unlocks cancelling an order whose food is already cooked.
    """

    cancel_unlocked_order: NotRequired[str]
    """Order the remedy ladder has now cleared for cancellation, if any.

    Set only when frustration is sustained *and* the policy layer would permit the
    cancellation. The prompt reads this to tell the agent to settle before escalating,
    instead of handing over a case it is now allowed to close.
    """
