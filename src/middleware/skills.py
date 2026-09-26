"""Skill injection.

Skills live as `src/skills/<category>/SKILL.md`. Rather than giving the model a
`load_skill` tool, the Jev category decides which skill is relevant and this middleware
appends exactly that one to the system prompt. The model never spends a turn choosing a
skill, and only one skill's tokens are ever in context.

The composed system prompt is: base prompt + soul + this turn's triage + the matching
skill + any escalation directive.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from src.classification.jev import Triage
from src.middleware.state import SupportState
from src.trace import SKILL_INJECTED, record_once, turn_of

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@lru_cache(maxsize=None)
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=None)
def load_skill(category: str) -> str:
    """Return a skill's body with its YAML frontmatter stripped.

    Returns an empty string for a category with no skill directory, so an unexpected
    Jev label degrades to the base prompt instead of raising.
    """
    path = SKILLS_DIR / category / "SKILL.md"
    if not path.exists():
        return ""

    text = _read(path)
    if text.startswith("---"):
        _, _, remainder = text.partition("---")
        _, _, body = remainder.partition("---")
        return body.strip()
    return text


def _triage_block(triage: Triage) -> str:
    mood = ["calm", "frustrated", "angry"][min(2, round(triage.frustration))]
    lines = [
        "## What the classifier saw in this message",
        "",
        f"- Category: **{triage.category}** (confidence {triage.category_confidence:.2f})",
        f"- Customer sounds: **{mood}** ({triage.frustration:.2f} on 0=calm, 2=angry)",
        f"- Urgent: **{'yes' if triage.is_urgent else 'no'}** ({triage.urgency:.2f})",
    ]
    if triage.category_confidence < 0.6:
        lines.append(
            "- The category is a weak guess. Confirm what the customer actually wants "
            "before acting on it."
        )
    if triage.is_upset:
        lines.append(
            "- Drop any warm-up. Lead with the substantive answer, not with pleasantries."
        )
    return "\n".join(lines)


@dynamic_prompt
def support_prompt(request: ModelRequest) -> str:
    """Compose the system prompt for this turn."""
    sections = [
        _read(PROMPTS_DIR / "system_prompt.md"),
        _read(PROMPTS_DIR / "soul.md"),
    ]

    state: SupportState = request.state  # type: ignore[assignment]
    raw_triage = state.get("triage")

    if raw_triage:
        triage = Triage.from_state(raw_triage)
        sections.append(_triage_block(triage))
        skill = load_skill(triage.category)
        record_once(
            SKILL_INJECTED,
            f"{triage.category}/SKILL.md ({len(skill)} chars)" if skill
            else f"no skill for category {triage.category}",
            {
                "category": triage.category,
                "skill_found": bool(skill),
                "skill_chars": len(skill),
                "escalation_directive": bool(state.get("escalation_required")),
                "cancel_unlocked_order": state.get("cancel_unlocked_order") or None,
            },
            customer_id=request.runtime.context.customer_id,
            turn=turn_of(state),
            dedupe_key=f"{triage.category}:{bool(state.get('escalation_required'))}",
        )
        if skill:
            sections.append(
                "## Playbook for this kind of request\n\n"
                "These instructions are specific to the category above and take "
                "precedence over your general habits.\n\n" + skill
            )

    unlocked = state.get("cancel_unlocked_order")

    if unlocked and not state.get("escalation_required"):
        # The remedy step did not land, but the stage ladder has opened up: the agent can
        # finish this itself, and a case the agent can close should not cost the customer
        # a wait in a human queue.
        sections.append(
            "## Settle this yourself\n\n"
            f"The remedy step is over and it did not land. Cancelling {unlocked} is now "
            f"permitted, so do it: call `cancel_order` for {unlocked} and tell the "
            f"customer plainly what came back, including the refund.\n\n"
            "Do not hand this to a human. You are now allowed to give them exactly what "
            "they have been asking for, and passing it on would make them wait again for "
            "an answer you already have. Do not ask them to confirm -- they have asked "
            "for this more than once already. Escalate only if the tool refuses."
        )

    if state.get("escalation_required"):
        note = state.get("escalation_note", "")
        if unlocked:
            sections.append(
                "## Settle this, then escalate\n\n"
                f"{note}\n\n"
                f"The remedy step is over. Cancelling {unlocked} is now permitted, so do "
                f"it: call `cancel_order` for {unlocked} first and tell the customer what "
                f"came back. Then call `escalate_to_human` with `priority=\"high\"` so a "
                f"person picks up the rest.\n\n"
                "Do it in that order. Handing over a case you are now allowed to close "
                "makes the customer wait twice. Do not ask them to confirm -- they have "
                "asked for this more than once already."
            )
        else:
            sections.append(
                "## This thread must be escalated\n\n"
                f"{note}\n\n"
                "Acknowledge the specific problem in one sentence, then call "
                "`escalate_to_human` with a reason a human can act on without rereading "
                "the thread. Use `priority=\"urgent\"` if illness, injury, or a safety "
                "incident is involved, otherwise `\"high\"`. Do not offer a refund or a "
                "workaround first, and do not ask the customer whether they would like to "
                "be escalated."
            )

    return "\n\n---\n\n".join(sections)
