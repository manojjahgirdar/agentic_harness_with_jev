"""Placeholder order tools.

Mostly read-only. Two exceptions: `report_missing_items` records a claim, and
`cancel_order` stops an undelivered order and reverses the charge. `cancel_order` moves
money, so like `issue_refund` it is guarded by `RefundPolicyMiddleware` -- the body here
assumes the guard has already had its say.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.context import SupportContext
from src.db.database import connect, fulfilment_stage, iso, parse, utcnow
from src.policy import evaluate_cancellation


def _customer_id(runtime: ToolRuntime[SupportContext, Any]) -> str:
    return runtime.context.customer_id


def _order_summary(row: Any) -> dict[str, Any]:
    now = utcnow()
    promised = parse(row["promised_at"])
    delivered = parse(row["delivered_at"])

    if delivered is not None:
        timing = {
            "delivered_at": row["delivered_at"],
            "minutes_vs_promise": int((delivered - promised).total_seconds() // 60),
        }
    else:
        timing = {
            "delivered_at": None,
            "minutes_late": max(0, int((now - promised).total_seconds() // 60)),
        }

    stage = fulfilment_stage(row["status"], row["courier"], row["delivered_at"])
    return {
        "order_id": row["order_id"],
        "restaurant": row["restaurant"],
        "status": row["status"],
        "fulfilment_stage": stage,
        "food_already_cooked": stage in {"awaiting_courier", "with_courier", "delivered"},
        "total_amount": row["total_amount"],
        "placed_at": row["placed_at"],
        "promised_at": row["promised_at"],
        "courier": row["courier"],
        **timing,
    }


@tool
def list_recent_orders(runtime: ToolRuntime[SupportContext, Any]) -> str:
    """List this customer's recent orders with status and delivery timing.

    Use this first when the customer has not named a specific order.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE customer_id = ? ORDER BY placed_at DESC LIMIT 10",
            (_customer_id(runtime),),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return "No orders found for this customer."
    return json.dumps([_order_summary(r) for r in rows], indent=2)


@tool
def track_order(order_id: str, runtime: ToolRuntime[SupportContext, Any]) -> str:
    """Get live status and delivery timing for one order by its ID.

    Args:
        order_id: The order reference, e.g. `ORD-1001`.
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, _customer_id(runtime)),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return f"No order {order_id} found for this customer."
    return json.dumps(_order_summary(row), indent=2)


@tool
def get_order_items(order_id: str, runtime: ToolRuntime[SupportContext, Any]) -> str:
    """List the line items on an order, including anything already flagged missing.

    Args:
        order_id: The order reference, e.g. `ORD-1003`.
    """
    conn = connect()
    try:
        owned = conn.execute(
            "SELECT 1 FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, _customer_id(runtime)),
        ).fetchone()
        if owned is None:
            return f"No order {order_id} found for this customer."
        rows = conn.execute(
            "SELECT name, quantity, unit_price, missing FROM order_items WHERE order_id = ?",
            (order_id,),
        ).fetchall()
    finally:
        conn.close()

    items = [
        {
            "name": r["name"],
            "quantity": r["quantity"],
            "unit_price": r["unit_price"],
            "line_total": round(r["quantity"] * r["unit_price"], 2),
            "reported_missing": bool(r["missing"]),
        }
        for r in rows
    ]
    return json.dumps(items, indent=2)


@tool
def report_missing_items(
    order_id: str,
    item_names: list[str],
    runtime: ToolRuntime[SupportContext, Any],
) -> str:
    """Flag items the customer says were not in the bag, and total their value.

    This records the claim and returns the amount at stake. It does not move money --
    call `issue_refund` separately if a refund is warranted.

    Args:
        order_id: The order reference.
        item_names: Names of the items that were missing, as they appear on the order.
    """
    conn = connect()
    try:
        owned = conn.execute(
            "SELECT 1 FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, _customer_id(runtime)),
        ).fetchone()
        if owned is None:
            return f"No order {order_id} found for this customer."

        matched: list[dict[str, Any]] = []
        unmatched: list[str] = []
        for name in item_names:
            row = conn.execute(
                "SELECT id, name, quantity, unit_price FROM order_items"
                " WHERE order_id = ? AND lower(name) = lower(?)",
                (order_id, name),
            ).fetchone()
            if row is None:
                unmatched.append(name)
                continue
            conn.execute("UPDATE order_items SET missing = 1 WHERE id = ?", (row["id"],))
            matched.append(
                {
                    "name": row["name"],
                    "quantity": row["quantity"],
                    "value": round(row["quantity"] * row["unit_price"], 2),
                }
            )
        conn.commit()
    finally:
        conn.close()

    return json.dumps(
        {
            "order_id": order_id,
            "flagged": matched,
            "not_on_order": unmatched,
            "value_at_stake": round(sum(m["value"] for m in matched), 2),
            "recorded_at": iso(utcnow()),
        },
        indent=2,
    )


@tool
def cancel_order(
    order_id: str,
    reason: str,
    runtime: ToolRuntime[SupportContext, Any],
) -> str:
    """Cancel an order and refund whatever cancelling it actually returns.

    What comes back depends on how far the order got: everything if the food has not been
    cooked, nothing once it has. Orders already with a courier cannot be cancelled at all,
    and an order sitting cooked waiting for a courier needs a goodwill remedy to have been
    tried first. The policy layer enforces all of that before this runs, so call it and
    read the result rather than predicting the outcome.

    Args:
        order_id: The order to cancel.
        reason: Short justification, recorded against the cancellation.
    """
    customer_id = runtime.context.customer_id

    # Must be evaluated on the same inputs the policy middleware used, or the guard and
    # the payout disagree: the middleware would permit a full refund on a stuck order
    # while this recomputed it as $0 and silently cancelled for nothing.
    state = runtime.state if isinstance(runtime.state, dict) else {}
    decision = evaluate_cancellation(
        customer_id=customer_id,
        order_id=order_id,
        frustration_sustained=bool(state.get("frustration_sustained")),
    )
    refund_amount = decision.refund_amount

    conn = connect()
    try:
        row = conn.execute(
            "SELECT status, total_amount FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, customer_id),
        ).fetchone()
        if row is None:
            return f"No order {order_id} found for this customer. Nothing cancelled."

        now = iso(utcnow())
        conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order_id,)
        )
        refund_id = None
        if refund_amount > 0:
            cursor = conn.execute(
                "INSERT INTO refunds (order_id, customer_id, amount, reason, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (order_id, customer_id, refund_amount, f"Order cancelled: {reason}", now),
            )
            refund_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    return json.dumps(
        {
            "order_id": order_id,
            "cancelled": True,
            "previous_status": row["status"],
            "order_total": row["total_amount"],
            "refund_amount": refund_amount,
            "refund_id": refund_id,
            "cancelled_at": now,
            "settles_in": "3-5 business days" if refund_amount else None,
        },
        indent=2,
    )
