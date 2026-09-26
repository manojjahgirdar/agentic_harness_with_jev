"""Letting the agent say it is finished."""

from __future__ import annotations

from typing import Any

from langchain.tools import ToolRuntime, tool

from src.context import SupportContext
from src.threads import CLOSED, set_status
from src.trace import THREAD_CLOSED, current_thread_id, current_turn, record


@tool
def close_conversation(
    resolution: str,
    runtime: ToolRuntime[SupportContext, Any],
) -> str:
    """Close this conversation once the customer's issue is fully resolved.

    Call this only when nothing is outstanding: the refund is issued, the order is
    tracked, the question is answered, and the customer has no open ask. Do not call it
    when you have escalated to a human, when an approval is still pending, or when you
    have promised a follow-up -- those conversations are still live, and closing one
    would stop the customer from replying.

    Args:
        resolution: One line on what was resolved, for the support team's record.
    """
    thread_id = current_thread_id()
    set_status(thread_id, CLOSED, by="agent", reason=resolution)

    record(
        THREAD_CLOSED,
        f"Closed by the agent — {resolution}",
        {"closed_by": "agent", "reason": resolution, "source": "agent"},
        customer_id=runtime.context.customer_id,
        thread_id=thread_id,
        turn=current_turn(thread_id),
    )
    return (
        "Conversation closed. Tell the customer it is resolved and that they can start a "
        "new chat if anything else comes up."
    )
