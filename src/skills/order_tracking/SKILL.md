---
name: order_tracking
description: Answer "where is my order" questions using live order status and delivery timing.
---

# Order tracking

1. If the customer named an order, call `track_order`. If they did not, call
   `list_recent_orders` and work out which one they mean — usually the most recent
   undelivered order. Ask only if two orders could plausibly match.
2. Report the concrete facts: restaurant, status, courier name, and how the timing
   compares to the promise. Say "about 20 minutes late" rather than "delayed".
3. Do not invent an ETA. The data gives you a promised time and a current status; if the
   order is out for delivery and late, say so and say you cannot see a precise new ETA.
4. **Then stop.** "Where is my order?" is a question, and the answer is where the order
   is. Someone who asked where their food is has not asked for compensation, and leading
   with one tells them you would rather pay them off than find their dinner. Remedies are
   for a customer who is dissatisfied, and you will know because they say so.

## When the customer wants to cancel a late order

Whether you can cancel depends on how far the order got, not on how firmly they asked.
`track_order` returns `fulfilment_stage` — read it before you say anything about
cancelling.

| `fulfilment_stage` | What you can do |
|---|---|
| `placed`, `preparing` | Cancel with `cancel_order`. Full refund, no approval needed. |
| `awaiting_courier` | **Voucher first.** Cooked food, no courier came. See below. |
| `with_courier` | **No cancellation.** The food is made and on its way. Offer a voucher. |
| `delivered` | Not a cancellation. Work out what went wrong and use `issue_refund`. |

Why: once the kitchen has cooked the food, that money is spent whatever the customer
decides. Cancelling then is not giving their money back, it is a second payment on top of
food nobody will eat. That is a decision a human makes, not you.

Never tell a customer you will refund an order whose food is already cooked. Check the
stage first.

## An order stuck waiting for a courier

`awaiting_courier` means the restaurant did its job and no driver came. It is the
platform's failure, and the customer may well be owed something — but the first move is
still to tell them what is happening.

1. Say plainly what happened: the food is ready and waiting on a driver. Do not hide
   behind "delayed". People are far more patient once they know the actual cause.
2. **If they only asked where their order is, that is the whole answer.** Do not reach
   for a voucher, and do not mention that one exists.
3. **If they are dissatisfied** — they ask to cancel, ask for their money back, say they
   have waited long enough, or are plainly upset — then a goodwill voucher is the right
   response. Call `issue_voucher` with the standard amount unless there is a reason not
   to.
4. **Do not offer to cancel, and do not call `cancel_order`.** It will be refused, and
   floating the option invites a fight you cannot settle.

If they are still angry on a later turn after all that, the situation has changed:
cancelling unlocks, and you will be told so in your context. When that happens, cancel it
and tell them — that is you finishing the case, not a reason to hand it over. A human is
only needed if the cancellation is refused and they still have an open ask.

### Never dangle a voucher

Every voucher is reviewed by a person, who may change the amount or refuse it. So there
is a window where you have asked for one and do not know the answer, and what you must
not do in that window is promise it, trail it, or use it to ask for patience.

Never write a sentence like *"I can arrange a goodwill voucher for the delay while you
keep waiting"*. It is a bribe for silence, offered before anyone agreed to pay it, and if
the reviewer says no you have made the second conversation worse than the first.

The rule is simple: **call the tool, and say nothing about a voucher until you know.**

- The tool comes back with a code → tell them plainly what was applied.
- The tool comes back refused, or the reviewer declined → **do not mention a voucher at
  all**, not even to report that there isn't one. "A delay voucher wasn't available"
  tells the customer they were considered for compensation and turned down, which is a
  worse answer than not raising it: now they want to know who decided, and why. Say what
  you *can* do — the order's status, the escalation, the ticket — and leave it there.

The same holds for anything else a guardrail has yet to grant. Offer what you *have*, not
what you hope someone will approve.

## Edge cases

- **Order is more than 45 minutes late and still undelivered.** Acknowledge the delay
  without being asked to — do not wait for the customer to get angry first. Then handle
  it yourself: say plainly what the hold-up is, and if they are unhappy about it, put a
  voucher in. A long wait is not a reason to hand the case to a queue, where they would
  wait again for the answer you already have. Escalate only if they ask for a human, or
  if the stage ladder leaves you with nothing to offer.
- **Order is late but still moving with a courier.** Do not cancel and do not refund. If
  they are unhappy about the delay, a voucher is the right size of response; if they only
  wanted to know where it is, tell them and leave it there.
- **Customer says "cancel it and refund me" about cooked food.** Do not argue policy at
  them and do not read them the stage table. Tell them the food is made and a driver is
  the hold-up. This one *is* a dissatisfied customer, so put a voucher in — and still say
  nothing about it until you know whether it was approved.
- **Order shows delivered but the customer says it never arrived.** This is not a
  tracking question. Confirm the address on file was correct, then treat it as a
  quality/refund case and check `get_refund_history` before offering anything.
- **Order not found.** Ask for the order reference rather than guessing.
