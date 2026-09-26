"""Middleware stack for the support agent.

Order matters. `create_agent` treats the first entry as the outermost layer:

0. `TraceMiddleware` — outermost, so its `wrap_tool_call` sees the final tool call and
   result after every other layer has had its say. Records to the `traces` table.
1. `JevTriageMiddleware` — classifies the turn; everything below reads its output.
2. `SummarizationMiddleware` — compacts the transcript before the prompt is built.
3. `support_prompt` — composes base prompt + soul + triage + the matching skill.
4. `ModelRouterMiddleware` — picks fast vs. reasoning model for this turn.
5. the risk gate — human approval, via `after_model`, before a flagged refund runs.
6. `RefundPolicyMiddleware` — refuses refunds policy forbids, around the tool call.

The last two must stay in that order. `wrap_tool_call` layers compose outermost-first,
and `HumanInTheLoopMiddleware` substitutes a reviewer's edited arguments inside its own
`wrap_tool_call`. If the policy check ran outside it, the policy would be evaluated
against the amount the *model* proposed while the tool executed the amount the
*reviewer* typed -- so a reviewer could edit a refund above the hard ceiling and the
ceiling would never see it. Keeping the policy check innermost means it always evaluates
the call that is actually about to run.
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain.agents.middleware import AgentMiddleware

from src.memory.memory import build_summarizer
from src.middleware.refund_policy import RefundPolicyMiddleware
from src.middleware.risk_gate import build_risk_gate
from src.middleware.routing import ModelRouterMiddleware, choose_model
from src.middleware.skills import load_skill, support_prompt
from src.middleware.state import SupportState
from src.middleware.tracing import TraceMiddleware
from src.middleware.triage import JevTriageMiddleware


def build_middleware(*, verbose: bool = True) -> Sequence[AgentMiddleware]:
    """Assemble the stack in execution order."""
    return [
        TraceMiddleware(),
        JevTriageMiddleware(),
        build_summarizer(),
        support_prompt,
        ModelRouterMiddleware(verbose=verbose),
        build_risk_gate(),
        RefundPolicyMiddleware(verbose=verbose),
    ]


__all__ = [
    "JevTriageMiddleware",
    "TraceMiddleware",
    "ModelRouterMiddleware",
    "RefundPolicyMiddleware",
    "SupportState",
    "build_middleware",
    "build_risk_gate",
    "choose_model",
    "load_skill",
    "support_prompt",
]
