"""Placeholder escalation tool: hands the thread to a human queue."""

from __future__ import annotations

import json
import uuid
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.context import SupportContext
from src.db.database import connect, iso, utcnow


@tool
def escalate_to_human(
    reason: str,
    runtime: ToolRuntime[SupportContext, Any],
    order_id: str | None = None,
    priority: str = "normal",
) -> str:
    """Hand this conversation to a human support agent and give the customer a ticket.

    Args:
        reason: What the human needs to know, in one or two sentences.
        order_id: The order involved, if there is one.
        priority: One of `normal`, `high`, or `urgent`.
    """
    customer_id = runtime.context.customer_id
    ticket_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
    now = iso(utcnow())

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO escalations (order_id, customer_id, reason, priority, created_at,"
            " ticket_id) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, customer_id, reason, priority, now, ticket_id),
        )
        conn.commit()
    finally:
        conn.close()

    return json.dumps(
        {
            "ticket_id": ticket_id,
            "priority": priority,
            "order_id": order_id,
            "created_at": now,
            "eta": "a human agent will pick this up within 15 minutes",
        },
        indent=2,
    )
