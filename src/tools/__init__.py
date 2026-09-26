"""Placeholder tool surface for the support agent."""

from src.tools.conversation_tools import close_conversation
from src.tools.escalation_tools import escalate_to_human
from src.tools.order_tools import (
    cancel_order,
    get_order_items,
    list_recent_orders,
    report_missing_items,
    track_order,
)
from src.tools.refund_tools import get_refund_history, issue_refund
from src.tools.voucher_tools import issue_voucher

SUPPORT_TOOLS = [
    list_recent_orders,
    track_order,
    get_order_items,
    report_missing_items,
    issue_voucher,
    cancel_order,
    get_refund_history,
    issue_refund,
    escalate_to_human,
    close_conversation,
]

MONEY_TOOLS = {"issue_refund", "cancel_order", "issue_voucher"}
"""Tools that move money and are guarded by `RefundPolicyMiddleware`."""

RISKY_TOOLS = {"issue_refund", "issue_voucher"}
"""Tools that pause for a human.

`issue_refund` pauses above the auto-approval limit or when Jev scores the call risky.
`issue_voucher` pauses *always* -- deciding what someone's goodwill is worth is the
human's call, and that pause is the whole point of the remedy step.

`cancel_order` is deliberately absent. It is not approved, it is *permitted or not* by
the stage ladder in `policy.evaluate_cancellation`, which already refuses every case
where a human would have said no.
"""

__all__ = [
    "MONEY_TOOLS",
    "close_conversation",
    "RISKY_TOOLS",
    "SUPPORT_TOOLS",
    "cancel_order",
    "escalate_to_human",
    "issue_voucher",
    "get_order_items",
    "get_refund_history",
    "issue_refund",
    "list_recent_orders",
    "report_missing_items",
    "track_order",
]
