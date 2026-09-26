"""Records what the agent actually did, as opposed to what it decided.

The other middleware trace their own decisions because only they know the reasoning.
This one sits across the whole loop and captures the observable behaviour: which tools
ran with which arguments, what came back, and what the customer was finally told. Those
are what a reader checks a decision against.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import Command

from src.context import SupportContext
from src.middleware.state import SupportState
from src.trace import AGENT_MESSAGE, TOOL_CALL, record, turn_of


class TraceMiddleware(AgentMiddleware[SupportState, SupportContext]):
    """Trace tool executions and the agent's final reply."""

    state_schema = SupportState

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        result = handler(request)

        content = result.content if isinstance(result, ToolMessage) else str(result)
        status = getattr(result, "status", "success")
        name = request.tool_call["name"]

        record(
            TOOL_CALL,
            f"{name}({_brief(request.tool_call['args'])})"
            + (" — refused" if status == "error" else ""),
            {
                "tool": name,
                "args": request.tool_call["args"],
                "status": status,
                "result": str(content)[:4000],
            },
            customer_id=request.runtime.context.customer_id,
            turn=turn_of(request.state),
        )
        return result

    def after_agent(
        self, state: SupportState, runtime: Runtime[SupportContext]
    ) -> dict[str, Any] | None:
        """Record the reply the customer actually saw."""
        messages = state.get("messages", [])
        reply = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage) and m.text), None
        )
        if reply is None:
            return None

        record(
            AGENT_MESSAGE,
            reply.text,
            {"text": reply.text, "model": (reply.response_metadata or {}).get("model_name")},
            customer_id=runtime.context.customer_id,
            turn=turn_of(state),
        )
        return None


def _brief(args: dict[str, Any]) -> str:
    """Compact argument rendering for the timeline's one-line summary."""
    parts = []
    for key, value in args.items():
        text = json.dumps(value) if not isinstance(value, str) else value
        parts.append(f"{key}={text[:40]}")
    return ", ".join(parts)
