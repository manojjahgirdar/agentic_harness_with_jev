"""Model routing driven by the Jev triage.

Cheap model for look-it-up questions, reasoning model for anything where getting it wrong
costs money or a customer. The decision is logged to stderr so the CLI can show which
model answered.
"""

from __future__ import annotations

import sys
from collections.abc import Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from src.classification.jev import Triage
from src.config import (
    REASONING_CATEGORIES,
    REASONING_NOUL_MIN,
)
from src.context import SupportContext
from src.middleware.state import SupportState
from src.models.openai import GPT5_5_FAST, GPT6_LUNA
from src.trace import MODEL_ROUTE, record, turn_of


def choose_model(state: SupportState) -> tuple[str, str]:
    """Return (`fast` | `reasoning`, why). Pure, so it can be unit tested."""
    raw = state.get("triage")
    if not raw:
        return "fast", "no triage yet"

    triage = Triage.from_state(raw)

    if state.get("escalation_required"):
        return "reasoning", "thread is being escalated"
    if triage.category in REASONING_CATEGORIES:
        return "reasoning", f"category {triage.category} carries a policy judgment"
    if triage.needs_reasoning >= REASONING_NOUL_MIN:
        return "reasoning", f"needs_reasoning {triage.needs_reasoning:.2f}"
    if triage.is_upset:
        return "reasoning", f"customer is upset ({triage.frustration:.2f}/2)"
    if triage.category_confidence < 0.6:
        return "reasoning", f"category is uncertain ({triage.category_confidence:.2f})"

    return "fast", f"{triage.category}, straightforward lookup"


class ModelRouterMiddleware(AgentMiddleware[SupportState, SupportContext]):
    """Swap the model per turn based on what Jev made of the message."""

    state_schema = SupportState

    def __init__(self, *, verbose: bool = True) -> None:
        self.verbose = verbose

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        tier, why = choose_model(request.state)  # type: ignore[arg-type]
        model = GPT6_LUNA if tier == "reasoning" else GPT5_5_FAST

        if self.verbose:
            print(f"  [route] {tier} model — {why}", file=sys.stderr)

        record(
            MODEL_ROUTE,
            f"{model.model_name} — {why}",
            {
                "tier": tier,
                "model": model.model_name,
                "reason": why,
                "triage": request.state.get("triage"),
            },
            customer_id=request.runtime.context.customer_id,
            turn=turn_of(request.state),
        )

        return handler(request.override(model=model))
