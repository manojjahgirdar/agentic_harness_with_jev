---
name: quality_concern
description: Handle complaints about the food itself — cold, stale, spoiled, or unsafe.
---

# Quality concerns

1. Lead with the apology, once, and make it specific to what they described. Then move to
   what you can do.
2. Call `track_order` to see how long the order took. Food that arrived very late gives
   the complaint independent support; food delivered on time does not make the customer
   wrong, but it does mean you should ask one clarifying question before paying out.
3. Call `get_order_items` to establish what the affected items are worth. Redress is
   capped at the value of the affected items, not the order total.

## Illness and safety — the one case that always goes to a human

If the customer reports illness, an allergic reaction, or a foreign object in the food,
stop working the refund. Call `escalate_to_human` with `priority="urgent"` immediately and
say that a human will take over. Never assess a health claim yourself and never imply the
food was safe.

This is the exception, not the pattern. Cold food, stale food, the wrong food, a small
portion, a rude note on the bag — all of those are yours to settle with a refund worth
the affected items.

## Edge cases

- **Vague complaint ("it was bad").** Ask one specific question — which item, and what was
  wrong with it — before acting.
- **Repeat complaint from the same customer.** Check `get_refund_history` first, then
  handle the complaint on its own facts and let `issue_refund` apply the policy — it
  refuses the histories that should be refused, and it does it without making an honest
  customer wait in a queue. Escalate only if it comes back refused and they are still
  asking.
- **They are angry about it.** Anger is not an escalation trigger. Be quick, be specific,
  and settle it.
