"""Goodwill vouchers: the remedy offered before anyone talks about cancelling.

A delay caused by no courier being available is the platform's fault, not the
restaurant's and not the customer's. The food is cooked and paid for, so a refund would
mean eating that cost twice. A voucher keeps the customer whole without doing that -- and
because it is a judgment call about someone's goodwill, a human decides the amount.

`issue_voucher` always pauses for human approval (see `risk_gate.py`). The agent proposes
the default; the reviewer approves it, edits the amount or validity, or rejects it.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

from langchain.tools import ToolRuntime, tool

from src.config import VOUCHER_DEFAULT_AMOUNT, VOUCHER_DEFAULT_DAYS
from src.context import SupportContext
from src.db.database import connect, iso, utcnow


@tool
def issue_voucher(
    reason: str,
    runtime: ToolRuntime[SupportContext, Any],
    order_id: str | None = None,
    amount: float = VOUCHER_DEFAULT_AMOUNT,
    valid_days: int = VOUCHER_DEFAULT_DAYS,
) -> str:
    """Offer the customer a credit voucher as goodwill for a delay.

    Use this when an order is late through no fault of the customer and the food has
    already been cooked -- a voucher costs the platform less than a refund and does not
    throw away food that is still coming. A human reviews every voucher before it is
    issued.

    Args:
        reason: What the voucher is compensating for, in one sentence.
        order_id: The order the delay relates to.
        amount: Voucher value in dollars. Leave at the default unless there is a reason.
        valid_days: How many days the voucher stays valid.
    """
    customer_id = runtime.context.customer_id
    code = f"TIF-{uuid.uuid4().hex[:6].upper()}"
    now = utcnow()

    conn = connect()
    try:
        conn.execute(
            "INSERT INTO vouchers (code, order_id, customer_id, amount, valid_days,"
            " reason, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                code,
                order_id,
                customer_id,
                amount,
                valid_days,
                reason,
                iso(now),
                iso(now + timedelta(days=valid_days)),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return json.dumps(
        {
            "voucher_code": code,
            "amount": amount,
            "valid_days": valid_days,
            "expires_at": iso(now + timedelta(days=valid_days)),
            "order_id": order_id,
        },
        indent=2,
    )
