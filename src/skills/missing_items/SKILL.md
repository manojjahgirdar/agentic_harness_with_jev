---
name: missing_items
description: Handle orders that arrived incomplete or with the wrong items.
---

# Missing items

1. Call `get_order_items` for the order so you are working from the real line items, not
   the customer's paraphrase.
2. Match what the customer describes to those item names. If nothing matches, say which
   items *were* on the order and ask which they mean — do not flag a guess.
3. Call `report_missing_items` with the matched names. It returns `value_at_stake`.
4. Offer redress worth no more than `value_at_stake`. That number is the ceiling for any
   refund on this complaint.

## Edge cases

- **Items already flagged.** `reported_missing: true` means this was raised before. Do
  not flag or refund the same item twice — check `get_refund_history` and, if it was
  already settled, explain that rather than paying again.
- **Customer claims the entire order is missing.** That is a non-delivery case, not a
  missing-items case. Check the order status first. If it is still out for delivery, say
  where it is. If it says delivered, ask the one question that settles it — was anything
  left with a neighbour or at the door — then treat it as a refund for the order total
  and let `issue_refund` decide: the guardrails already refuse the amounts and the
  histories that a human would refuse. Escalate only if that refusal comes back and they
  are still asking.
- **Value at stake is above the auto-approval limit.** Request the refund anyway and say
  it is being reviewed. A reviewer deciding an amount is not a handoff — stay in the
  conversation and tell them the answer when it comes.
- **Customer has raised missing items before.** Check `get_refund_history` and judge this
  complaint on its own facts. A pattern is for the guardrails to act on, not a reason to
  transfer someone who may simply have had two bad orders.
