# Support Dashboard

The internal application: what the agent decided, why, and what is waiting on a human. It
is a view over `src/api.py` -- every number on screen comes from the `traces` table, and
nothing is recomputed in the browser.

The customer's side lives in `../chat`, a separate application. Nothing here is meant for
a customer to see, which is exactly why the two are not one app with a route guard.

```bash
npm run dev     # :3000, expects the support API on :8000
```

`NEXT_PUBLIC_API_URL` overrides the API location (default `http://127.0.0.1:8000`).

## Pages

- `app/page.tsx` -- every thread as a table row: type, the fast model's intent summary,
  the customer's opening query, open/closed status, whether it escalated, the frustration
  curve across turns, and a delete. Flat rather than grouped by customer, because "which conversation needs
  me" does not respect customer boundaries. Ten rows a page; clicking a row opens it.
  Above the table, `ActionQueue` lists the threads blocked on a person and
  `AttentionStrip` those whose frustration has passed the watchlist threshold, still-moving
  ones first.
- `app/threads/[threadId]/page.tsx` -- one thread's full trace as a centred pane: the
  turn-by-turn timeline, any approval waiting on a decision, and the composer for
  answering an escalated thread as a human.

## Components

| file | what it draws |
| --- | --- |
| `ThreadTable.tsx` | the thread list, paged, with delete behind an in-row confirm |
| `StatusControl.tsx` | close a resolved thread, or reopen one |
| `ActionQueue.tsx` | approvals and escalations waiting on a human |
| `AttentionStrip.tsx` | live threads worth a look before they escalate |
| `TraceView.tsx` | a thread's header, state flags, and timeline |
| `EventCard.tsx` | one traced decision, styled per event type |
| `Meters.tsx` | the Jev readouts -- confidence bars, rubric meters, sparklines |
| `ApprovalPanel.tsx` | approve / edit / reject on a paused tool call |
| `HumanReply.tsx` | reply as support on an escalated thread |

`lib/useTraceStream.ts` subscribes to the API's SSE stream; both pages refetch from it, so
a conversation in the terminal shows up here as it happens.

## Conventions

- Colour comes from the tokens in `app/globals.css` (`--jev`, `--allow`, `--deny`,
  `--review`, `--human`, ...), never hard-coded hex. Each event type maps to one accent,
  and that mapping is the legend the whole timeline reads by.
- Anything the model or a classifier produced is shown with the number that produced it,
  and with the threshold it was judged against.
