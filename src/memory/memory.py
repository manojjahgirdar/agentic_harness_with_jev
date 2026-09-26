"""Thread persistence and conversation compaction.

Two different things both called "memory":

- **Thread memory** is the SQLite checkpointer. Every turn of every thread is written to
  `harness.db`, so a conversation survives the process exiting -- and, just as important,
  an interrupted refund can be resumed after the human decides.
- **Working memory** is `SummarizationMiddleware`, which replaces old turns with a summary
  once the transcript gets long, keeping the last few messages verbatim.
"""

from __future__ import annotations

import sqlite3

from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver

from src.config import DB_PATH, KEEP_LAST_MESSAGES, SUMMARIZE_AFTER_TOKENS
from src.models.openai import SUMMARIZER


def build_checkpointer() -> SqliteSaver:
    """Open the SQLite checkpointer against the shared harness database.

    The connection is opened with `check_same_thread=False` because LangGraph may touch
    it from a worker thread. `SqliteSaver` serializes its own writes behind a lock.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def build_summarizer() -> SummarizationMiddleware:
    """Compact the thread once it passes the token budget."""
    return SummarizationMiddleware(
        model=SUMMARIZER,
        trigger=("tokens", SUMMARIZE_AFTER_TOKENS),
        keep=("messages", KEEP_LAST_MESSAGES),
        summary_prompt=(
            "Summarize this food-delivery support conversation for the agent that will "
            "continue it.\n\n"
            "Preserve exactly: order IDs and their status, amounts already refunded or "
            "promised, items reported missing, any ticket IDs from escalations, and any "
            "commitment made to the customer. Note the customer's mood if it changed.\n\n"
            "Drop pleasantries and repeated apologies.\n\n"
            "Messages to summarize:\n{messages}"
        ),
    )
