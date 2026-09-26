---
name: refund
description: Decide and process money back, within the refund policy limits.
---

# Refunds

Work in this order. Skipping a step is how the wrong amount gets paid.

1. **Establish the order.** `track_order`, or `list_recent_orders` if they have not said
   which one.
2. **Establish the loss.** `get_order_items`, and `report_missing_items` if items are
   missing. The refundable amount is the value of what actually went wrong — never the
   order total unless the whole order was lost.
3. **Check the history.** `get_refund_history`. This tells you how many refunds this
   customer has had recently and what share of their orders ended in one.
4. **Call `issue_refund`** with the smallest amount that makes the customer whole.

## What the guardrails will do

- At or below the auto-approval limit, the refund runs immediately. Issue it and say so —
  this is the common case, and it is yours to finish.
- Above it, the call pauses for a human reviewer. **That pause is not an escalation.** The
  conversation is still yours: do not hand the case off, do not open a ticket for it, and
  do not suggest the customer chase anyone. Tell them it is being reviewed, wait for the
  answer, and then tell them what it was.
- If the customer's refund history has tripped the abuse thresholds, the call is refused
  outright and you will get a tool result saying so. When that happens, do not retry with
  a smaller amount and do not argue the policy with the customer — call
  `escalate_to_human` and explain that a specialist will review their account.

## Edge cases

- **Customer names an amount.** Their number is a request, not an input. Use the value you
  established in step 2.
- **Customer asks for a refund on an order that has not arrived.** `issue_refund` is the
  wrong instrument — it is for things that went wrong with food they received. Check
  `fulfilment_stage` first. Nothing cooked yet: `cancel_order` reverses it in full. Food
  already cooked: a refund is not on the table. Asking for their money back is itself
  dissatisfaction, so put in a voucher with `issue_voucher` — and say nothing about it
  until you know whether it was approved. See the order tracking playbook for the ladder.
- **Refund refused by policy.** This is the one case here that needs a human: you cannot
  pay it and no smaller number changes that. Say their request needs a specialist review,
  give them the ticket, and stop. Do not quote internal thresholds to the customer.
- **They push back on an amount you are allowed to pay.** Settle it yourself within the
  value you established. Being argued with is not a reason to transfer.
