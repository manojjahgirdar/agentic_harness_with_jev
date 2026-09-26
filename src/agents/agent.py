"""The support agent.

Everything the agent is made of lives in its own module; this assembles them. Note there
is no `system_prompt=` argument -- `support_prompt` builds the system message per turn
from the Jev triage, so passing a static one here would be overwritten.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from src.context import SupportContext
from src.db.database import init_db
from src.memory.memory import build_checkpointer
from src.middleware import build_middleware
from src.models.openai import GPT5_5_FAST
from src.tools import SUPPORT_TOOLS


def build_support_agent(*, verbose: bool = True) -> CompiledStateGraph:
    """Create the agent with persistence, middleware, and placeholder tools wired up."""
    init_db()

    return create_agent(
        model=GPT5_5_FAST,  # default only; ModelRouterMiddleware overrides per turn
        tools=SUPPORT_TOOLS,
        middleware=build_middleware(verbose=verbose),
        context_schema=SupportContext,
        checkpointer=build_checkpointer(),
        name="tiffin_support",
    )
