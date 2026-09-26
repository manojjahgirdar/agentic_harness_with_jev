"""Placeholder refund tools.

`issue_refund` is the one genuinely dangerous tool in the harness, so it is guarded
twice: `HumanInTheLoopMiddleware` can interrupt before it runs, and
`RefundPolicyMiddleware` wraps the call itself. The tool body assumes both have already
had their say and simply writes the row.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.context import SupportContext
from src.db.database import connect, iso, utcnow
from src.policy import refund_history


@tool
def get_refund_history(runtime: ToolRuntime[SupportContext, Any]) -> str:
    """Show this customer's past refunds and how they compare to policy limits.

    Check this before promising a refund.
    """
    customer_id = runtime.context.customer_id
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT order_id, amount, reason, created_at, status FROM refunds"
            " WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,),
        ).fetchall()
    finally:
        conn.close()

    recent, rate = refund_history(customer_id)
    return json.dumps(
        {
            "refunds": [dict(r) for r in rows],
            "refunds_in_window": recent,
            "share_of_orders_refunded": round(rate, 2),
        },
        indent=2,
    )


@tool
def issue_refund(
    order_id: str,
    amount: float,
    reason: str,
    runtime: ToolRuntime[SupportContext, Any],
) -> str:
    """Refund money to the customer for an order.

    Only call this once you have confirmed the order exists and established what went
    wrong. Refunds above the auto-approval limit are routed to a human before they run.

    Args:
        order_id: The order being refunded.
        amount: Amount in dollars. Never exceed the value actually at stake.
        reason: Short justification, recorded on the refund row.
    """
    customer_id = runtime.context.customer_id
    conn = connect()
    try:
        order = conn.execute(
            "SELECT total_amount FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, customer_id),
        ).fetchone()
        if order is None:
            return f"No order {order_id} found for this customer. Nothing refunded."
        if amount > order["total_amount"]:
            return (
                f"Refused: ${amount:.2f} exceeds the ${order['total_amount']:.2f} order "
                f"total. Nothing refunded."
            )

        now = iso(utcnow())
        cursor = conn.execute(
            "INSERT INTO refunds (order_id, customer_id, amount, reason, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (order_id, customer_id, amount, reason, now),
        )
        conn.commit()
        refund_id = cursor.lastrowid
    finally:
        conn.close()

    return json.dumps(
        {
            "refund_id": refund_id,
            "order_id": order_id,
            "amount": amount,
            "reason": reason,
            "issued_at": now,
            "settles_in": "3-5 business days",
        },
        indent=2,
    )
