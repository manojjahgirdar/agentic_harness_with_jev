"""Single place for every tunable in the support harness.

Thresholds live here rather than inline so policy can be changed without touching
middleware logic.
"""

from __future__ import annotations

from pathlib import Path

import dotenv

dotenv.load_dotenv()

# --- Storage -----------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "harness.db"
"""One SQLite file holds both LangGraph checkpoints and the fake business tables."""

# --- Models ------------------------------------------------------------------

FAST_MODEL = "openai:gpt-5.4-mini"
"""Cheap path: greetings, status lookups, single-fact answers.

`gpt-5.5-fast` is not a model ID this account can reach (the API 404s it); `gpt-5.5` is
the nearest real one. Swap this line if a faster tier becomes available.
"""

REASONING_MODEL = "openai:gpt-6-astra"
"""Deliberate path: refunds, disputes, anything with a policy judgment in it."""

SUMMARY_MODEL = FAST_MODEL
"""Model used by SummarizationMiddleware to compact old turns."""

TITLE_MODEL = FAST_MODEL
"""Model that names a thread by its intent. Deliberately the cheap one: it runs once per
thread, off the conversation's critical path, and a title is not a judgment call."""

TITLE_MAX_WORDS = 6
"""Upper bound on a generated thread title, enforced after generation as well as asked."""

TITLE_BATCH_LIMIT = 12
"""Most titles written in one pass, so a first dashboard load cannot stall on a backlog."""

# --- Watchlist ---------------------------------------------------------------

ATTENTION_FRUSTRATION = 0.50
"""Frustration above this on a live thread is worth a reviewer's attention.

Well below `ESCALATE_FRUSTRATION`: the point is to surface a conversation while there is
still time to change how it ends, not to report one that already went wrong.
"""

ATTENTION_WINDOW_MINUTES = 15
"""How recently a thread must have moved to still count as live.

This marks a watchlist card, it does not filter one out. A thread that went badly and
then went quiet is exactly the one worth noticing, so it stays on the list and simply
stops being flagged live.
"""

# --- Conversation memory -----------------------------------------------------

SUMMARIZE_AFTER_TOKENS = 3000
"""Summarize once the transcript passes this many tokens."""

KEEP_LAST_MESSAGES = 6
"""Verbatim messages preserved after a summarization pass."""

# --- Refund policy -----------------------------------------------------------

REFUND_AUTO_MAX = 25.00
"""Refunds at or below this amount execute without human approval."""

REFUND_HARD_MAX = 200.00
"""No refund above this is ever issued by the agent, approved or not."""

ABUSE_REFUND_COUNT = 3
"""Refund count within the window that marks a customer as an abuse risk."""

ABUSE_WINDOW_DAYS = 30
"""Lookback window for the refund count above."""

ABUSE_REFUND_RATE = 0.50
"""Share of a customer's orders that ending in a refund also marks abuse."""

# --- Cancellation, by fulfilment stage ---------------------------------------
#
# What a cancellation costs depends entirely on how far the order got. Before the
# restaurant starts, nothing has been spent and the customer gets everything back. Once
# the food is cooked, that money is gone whatever the customer decides -- so a "cancel
# and refund" at that point is a goodwill payment, not a reversal, and it is not the
# agent's to hand out.

CANCEL_FULL_REFUND_STAGES = {"placed", "preparing"}
"""Stages where cancelling returns the full order total, no approval needed."""

CANCEL_BLOCKED_STAGES = {"with_courier"}
"""Stages where cancelling is refused outright.

The food is cooked and a courier is carrying it. Cancelling returns nothing and strands a
delivery, so the agent offers a remedy or escalates instead.
"""

CANCEL_NEEDS_REMEDY_FIRST_STAGES = {"awaiting_courier"}
"""Stages where a remedy is tried before cancellation is even considered.

The restaurant cooked the food and no courier has collected it -- a platform failure, not
the restaurant's and not the customer's. A human decides what to offer. Cancellation
unlocks only once frustration is sustained (see `FRUSTRATION_TURNS_FOR_CANCEL`).
"""

# --- Goodwill vouchers -------------------------------------------------------

VOUCHER_DEFAULT_AMOUNT = 5.00
"""Opening offer for a delay the platform caused."""

VOUCHER_DEFAULT_DAYS = 5
"""How long that voucher stays valid."""

VOUCHER_MAX_AMOUNT = 15.00
"""Ceiling a reviewer may raise a voucher to."""

# --- Sustained frustration ---------------------------------------------------

FRUSTRATION_TURNS_FOR_CANCEL = 2
"""Upset turns that count as sustained anger even without a further rise."""

FRUSTRATION_RISE_FOR_CANCEL = 0.2
"""How much frustration must climb between turns to count as "still building".

Frustration that is *rising* matters more than frustration that is merely high. A
customer who came in annoyed and got angrier after being offered a voucher has told you
the remedy did not work, and that is the signal to stop offering and start settling --
even though they have only crossed the upset line once.
"""

VOUCHER_ONE_PER_ORDER = True
"""Refuse a second goodwill voucher on the same order.

Without this the agent answers renewed anger by offering the same remedy again, which
reads as stalling. One voucher per delay; after that the ladder has to move on.
"""

# --- Escalation --------------------------------------------------------------

ESCALATE_FRUSTRATION = 1.5
"""Jev frustration Score (0=calm, 1=frustrated, 2=angry) that counts as upset."""

ESCALATE_LATE_MINUTES = 45
"""Minutes past the promised delivery time that counts as badly late.

Despite the name this no longer forces an escalation -- that rule sent most unhappy
customers to a human for something the agent could settle. It marks the delay as serious,
which changes the agent's urgency and an escalation's `priority`, not who handles it.
"""

URGENCY_NOUL_MIN = 0.70
"""Jev urgency Noul probability at or above which a message is treated as urgent."""

# --- Model routing -----------------------------------------------------------

REASONING_NOUL_MIN = 0.50
"""Jev `needs_reasoning` probability at or above which the reasoning model is used."""

REASONING_CATEGORIES = {"refund", "quality_concern", "escalation"}
"""Categories that always get the reasoning model regardless of the Noul."""

# --- Tool risk gating --------------------------------------------------------

TOOL_RISK_REVIEW_MIN = 1.5
"""Jev tool-risk Score (0=routine, 1=notable, 2=severe) that forces human review."""
