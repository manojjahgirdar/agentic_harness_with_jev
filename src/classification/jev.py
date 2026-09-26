"""Jev (TypeSafe) classification for the support harness.

Two classifiers live here:

- `classify_message` runs once per user turn and produces the `Triage` record that the
  routing, skill-injection, and escalation middleware all read.
- `score_tool_risk` runs only when a gated tool is about to fire, and feeds the
  human-in-the-loop predicate.

Keeping both in one module means the question wording -- the part that actually decides
behavior -- is reviewable in a single place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_typesafe import Choice, Noul, Score, TypeSafeClassifier

CATEGORIES = {
    "order_tracking": (
        "Where is my order, how long until it arrives, delivery status, courier "
        "location, or changing the delivery address."
    ),
    "missing_items": (
        "The order arrived but something was left out, the wrong item was sent, or the "
        "quantity is short."
    ),
    "quality_concern": (
        "The food arrived but was cold, stale, spilled, undercooked, or made someone "
        "unwell. Complaints about the food itself rather than what was in the bag."
    ),
    "refund": (
        "The customer is explicitly asking for money back, a credit, or a charge to be "
        "reversed."
    ),
    "escalation": (
        "The customer wants a human agent, a manager, is threatening legal action or a "
        "chargeback, or is reporting a safety incident."
    ),
}

FRUSTRATION_LEVELS = [
    "Calm and neutral. Asking a question or sharing information without complaint.",
    "Frustrated. Clearly unhappy, impatient, or complaining, but still civil.",
    "Angry. Hostile, insulting, shouting in capitals, or threatening to leave or sue.",
]

TOOL_RISK_LEVELS = [
    "Routine. Reading data or a small, clearly justified change.",
    "Notable. Moves money or changes an order in a way worth a second look.",
    "Severe. Large or poorly justified payout, or an action the conversation does not "
    "support.",
]

_classifier = TypeSafeClassifier()


@dataclass(frozen=True)
class Triage:
    """One Jev pass over the newest user message."""

    category: str
    category_confidence: float
    urgency: float
    frustration: float
    needs_reasoning: float
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_urgent(self) -> bool:
        from src.config import URGENCY_NOUL_MIN

        return self.urgency >= URGENCY_NOUL_MIN

    @property
    def is_upset(self) -> bool:
        from src.config import ESCALATE_FRUSTRATION

        return self.frustration >= ESCALATE_FRUSTRATION

    def to_state(self) -> dict[str, Any]:
        """Serialize into something a LangGraph checkpoint can round-trip."""
        return {
            "category": self.category,
            "category_confidence": self.category_confidence,
            "urgency": self.urgency,
            "frustration": self.frustration,
            "needs_reasoning": self.needs_reasoning,
        }

    @classmethod
    def from_state(cls, data: dict[str, Any]) -> Triage:
        return cls(
            category=data["category"],
            category_confidence=data["category_confidence"],
            urgency=data["urgency"],
            frustration=data["frustration"],
            needs_reasoning=data["needs_reasoning"],
        )


def classify_message(text: str) -> Triage:
    """Classify one customer message into category, urgency, mood, and complexity."""
    response = _classifier.invoke(
        {
            "state": text,
            "questions": {
                "category": Choice(
                    instructions=(
                        "Which support workflow should handle this customer message for "
                        "a food delivery service?"
                    ),
                    criteria=CATEGORIES,
                ),
                "urgency": Noul(
                    instructions=(
                        "Does this message need attention right now rather than in the "
                        "normal queue?"
                    ),
                ),
                "frustration": Score(
                    instructions="How frustrated does this customer sound?",
                    criteria=FRUSTRATION_LEVELS,
                ),
                "needs_reasoning": Noul(
                    instructions=(
                        "Answering this well requires weighing policy, reconciling "
                        "conflicting details, or planning several steps -- as opposed to "
                        "looking up one fact and reporting it."
                    ),
                ),
            },
        }
    )

    category = response.choices["category"]
    return Triage(
        category=category.choice,
        category_confidence=category.confidence,
        urgency=response.nouls["urgency"].noul,
        frustration=response.scores["frustration"].score,
        needs_reasoning=response.nouls["needs_reasoning"].noul,
    )


def score_tool_risk(*, tool_name: str, args: dict[str, Any], conversation: str) -> float:
    """Score how risky one proposed tool call looks given the conversation so far.

    Returns the expected value on the 0-2 `TOOL_RISK_LEVELS` rubric, so a fractional
    result such as `1.4` is normal.
    """
    response = _classifier.invoke(
        {
            "state": {
                "proposed_action": {"tool": tool_name, "arguments": args},
                "conversation": conversation,
            },
            "questions": {
                "risk": Score(
                    instructions=(
                        "A support agent wants to run `proposed_action`. Judging only by "
                        "what the customer has actually established in `conversation`, "
                        "how risky is letting it run unsupervised?"
                    ),
                    criteria=TOOL_RISK_LEVELS,
                )
            },
        }
    )
    return response.scores["risk"].score
