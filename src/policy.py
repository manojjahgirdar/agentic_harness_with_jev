"""Deterministic business rules, kept separate from both tools and middleware.

The refund gate is evaluated in two places -- the human-in-the-loop `when` predicate
(before the tool runs) and `RefundPolicyMiddleware` (around the tool call). Both call
`evaluate_refund` so a policy change lands in one place and the two can never drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from src.config import (
    ABUSE_REFUND_COUNT,
    VOUCHER_ONE_PER_ORDER,
    CANCEL_BLOCKED_STAGES,
    CANCEL_FULL_REFUND_STAGES,
    CANCEL_NEEDS_REMEDY_FIRST_STAGES,
    ABUSE_REFUND_RATE,
    ABUSE_WINDOW_DAYS,
    ESCALATE_LATE_MINUTES,
    REFUND_AUTO_MAX,
    REFUND_HARD_MAX,
)
from src.db.database import connect, fulfilment_stage, parse, utcnow

Verdict = Literal["allow", "review", "deny"]


@dataclass(frozen=True)
class RefundDecision:
    verdict: Verdict
    reason: str
    amount: float
    recent_refund_count: int
    refund_rate: float

    @property
    def abusive(self) -> bool:
        return (
            self.recent_refund_count >= ABUSE_REFUND_COUNT
            or self.refund_rate > ABUSE_REFUND_RATE
        )


@dataclass(frozen=True)
class CancellationDecision:
    verdict: Verdict
    reason: str
    refund_amount: float
    """What cancelling actually returns. Zero once the food has been cooked."""
    order_total: float
    stage: str
    remedy_first: bool = False
    """True when a goodwill remedy should be offered before cancelling is considered."""


@dataclass(frozen=True)
class LateOrder:
    order_id: str
    restaurant: str
    status: str
    minutes_late: int


def refund_history(customer_id: str) -> tuple[int, float]:
    """Return (refunds in the abuse window, share of all orders ever refunded)."""
    conn = connect()
    try:
        cutoff = (utcnow() - timedelta(days=ABUSE_WINDOW_DAYS)).isoformat()
        recent = conn.execute(
            "SELECT COUNT(*) FROM refunds WHERE customer_id = ? AND created_at >= ?",
            (customer_id, cutoff),
        ).fetchone()[0]
        total_orders = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]
        refunded_orders = conn.execute(
            "SELECT COUNT(DISTINCT order_id) FROM refunds WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    rate = (refunded_orders / total_orders) if total_orders else 0.0
    return recent, rate


def evaluate_refund(*, customer_id: str, amount: float) -> RefundDecision:
    """Decide whether a refund may run unsupervised, needs a human, or is refused."""
    recent, rate = refund_history(customer_id)

    if amount > REFUND_HARD_MAX:
        return RefundDecision(
            verdict="deny",
            reason=(
                f"${amount:.2f} is above the ${REFUND_HARD_MAX:.2f} ceiling the agent may "
                f"ever authorize, with or without approval."
            ),
            amount=amount,
            recent_refund_count=recent,
            refund_rate=rate,
        )

    if recent >= ABUSE_REFUND_COUNT:
        return RefundDecision(
            verdict="deny",
            reason=(
                f"{recent} refunds already issued to this customer in the last "
                f"{ABUSE_WINDOW_DAYS} days (limit is {ABUSE_REFUND_COUNT})."
            ),
            amount=amount,
            recent_refund_count=recent,
            refund_rate=rate,
        )

    if rate > ABUSE_REFUND_RATE:
        return RefundDecision(
            verdict="deny",
            reason=(
                f"{rate:.0%} of this customer's orders have ended in a refund, above the "
                f"{ABUSE_REFUND_RATE:.0%} threshold."
            ),
            amount=amount,
            recent_refund_count=recent,
            refund_rate=rate,
        )

    if amount > REFUND_AUTO_MAX:
        return RefundDecision(
            verdict="review",
            reason=(
                f"${amount:.2f} is above the ${REFUND_AUTO_MAX:.2f} auto-approval limit."
            ),
            amount=amount,
            recent_refund_count=recent,
            refund_rate=rate,
        )

    return RefundDecision(
        verdict="allow",
        reason=f"${amount:.2f} is within the ${REFUND_AUTO_MAX:.2f} auto-approval limit.",
        amount=amount,
        recent_refund_count=recent,
        refund_rate=rate,
    )


def badly_late_orders(customer_id: str) -> list[LateOrder]:
    """Undelivered orders more than `ESCALATE_LATE_MINUTES` past their promise.

    No longer an escalation trigger. Being very late with an upset customer used to force
    a handoff, which sent most unhappy customers to a human for a problem the agent could
    answer; the remedy ladder handles it instead. Kept as the definition of "badly late",
    which the skills still reason with.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT order_id, restaurant, status, promised_at FROM orders"
            " WHERE customer_id = ? AND delivered_at IS NULL AND status != 'cancelled'",
            (customer_id,),
        ).fetchall()
    finally:
        conn.close()

    now = utcnow()
    late: list[LateOrder] = []
    for row in rows:
        promised = parse(row["promised_at"])
        if promised is None:
            continue
        minutes_late = int((now - promised).total_seconds() // 60)
        if minutes_late > ESCALATE_LATE_MINUTES:
            late.append(
                LateOrder(
                    order_id=row["order_id"],
                    restaurant=row["restaurant"],
                    status=row["status"],
                    minutes_late=minutes_late,
                )
            )
    return sorted(late, key=lambda o: o.minutes_late, reverse=True)


def evaluate_cancellation(
    *,
    customer_id: str,
    order_id: str,
    frustration_sustained: bool = False,
) -> CancellationDecision:
    """Decide whether an order may be cancelled, and what cancelling returns.

    The answer turns on how far the order got, because that determines whether the money
    still exists. Before the food is cooked, cancelling is a reversal and the customer
    gets everything back. After it is cooked, the spend is sunk: cancelling is a goodwill
    payment, and the agent does not make those alone.

    `frustration_sustained` is the release valve. An order stuck waiting for a courier is
    a platform failure, so a remedy is offered first -- but a customer who is still angry
    after that should not be held in the loop, and cancellation unlocks.
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT status, total_amount, delivered_at, courier FROM orders"
            " WHERE order_id = ? AND customer_id = ?",
            (order_id, customer_id),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return CancellationDecision(
            verdict="deny",
            reason=f"No order {order_id} found for this customer.",
            refund_amount=0.0,
            order_total=0.0,
            stage="unknown",
        )

    total = row["total_amount"]
    stage = fulfilment_stage(row["status"], row["courier"], row["delivered_at"])

    def decision(verdict: Verdict, reason: str, refund: float, **kw) -> CancellationDecision:
        return CancellationDecision(
            verdict=verdict,
            reason=reason,
            refund_amount=refund,
            order_total=total,
            stage=stage,
            **kw,
        )

    if stage == "cancelled":
        return decision("deny", f"Order {order_id} is already cancelled.", 0.0)

    if stage == "delivered":
        return decision(
            "deny",
            f"Order {order_id} has already been delivered, so it cannot be cancelled. "
            f"Work out what actually went wrong and use `issue_refund`.",
            0.0,
        )

    if stage in CANCEL_BLOCKED_STAGES:
        return decision(
            "deny",
            f"Order {order_id} has been cooked and courier {row['courier']} is carrying "
            f"it. Cancelling now returns $0.00 -- the food is paid for and the delivery is "
            f"already in motion. Offer a goodwill voucher for the delay, or escalate.",
            0.0,
        )

    if stage in CANCEL_NEEDS_REMEDY_FIRST_STAGES and not frustration_sustained:
        return decision(
            "deny",
            f"Order {order_id} is cooked and waiting for a courier, so the ${total:.2f} is "
            f"already spent. A goodwill voucher comes first; cancelling is only on the "
            f"table if the customer is still unhappy after that.",
            0.0,
            remedy_first=True,
        )

    # Either nothing has been cooked, or the remedy did not land and frustration persists.
    if total > REFUND_HARD_MAX:
        return decision(
            "deny",
            f"${total:.2f} is above the ${REFUND_HARD_MAX:.2f} ceiling the agent may ever "
            f"authorize.",
            0.0,
        )

    recent, rate = refund_history(customer_id)
    if recent >= ABUSE_REFUND_COUNT or rate > ABUSE_REFUND_RATE:
        return decision(
            "deny",
            f"This customer has had {recent} refunds in the last {ABUSE_WINDOW_DAYS} days "
            f"and {rate:.0%} of their orders refunded.",
            0.0,
        )

    if stage in CANCEL_FULL_REFUND_STAGES:
        why = f"Order {order_id} is {stage} and nothing has been cooked yet."
    else:
        why = (
            f"Order {order_id} is stuck at {stage} and the customer is still unhappy after "
            f"a remedy was offered."
        )
    return decision("allow", why, total)


def existing_voucher(customer_id: str, order_id: str | None) -> dict[str, object] | None:
    """The goodwill voucher already issued on this order, if there is one."""
    if not VOUCHER_ONE_PER_ORDER or not order_id:
        return None
    conn = connect()
    try:
        row = conn.execute(
            "SELECT code, amount, valid_days, created_at FROM vouchers"
            " WHERE customer_id = ? AND order_id = ? ORDER BY id DESC LIMIT 1",
            (customer_id, order_id),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def cancellable_stuck_order(customer_id: str) -> str:
    """The undelivered order sustained frustration has now cleared for cancellation.

    Returns an empty string when there is none -- including when the only late order is
    already with a courier, which no amount of frustration makes cancellable.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT order_id FROM orders WHERE customer_id = ? AND delivered_at IS NULL"
            " AND status NOT IN ('cancelled', 'delivered') ORDER BY placed_at",
            (customer_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        decision = evaluate_cancellation(
            customer_id=customer_id,
            order_id=row["order_id"],
            frustration_sustained=True,
        )
        if decision.verdict == "allow":
            return row["order_id"]
    return ""
