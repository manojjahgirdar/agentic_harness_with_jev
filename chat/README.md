# Support Chat

The customer-facing application. A customer talks to Tiffin support here, sees their own
conversations down the left, and can delete any of them.

```bash
npm run dev     # :3001, expects the support API on :8000
```

It is a separate application from the Support Dashboard (`../dashboard`) because it has a
different audience. Everything the dashboard exists to show -- tool calls, policy
verdicts, Jev scores, the approval queue, other customers -- is not a customer's business,
and the cleanest way to guarantee that is for the customer-facing app not to have the
routes at all. `lib/api.ts` is the whole surface it can reach, and it is scoped to one
customer.

## What the customer sees

- **Their conversations**, newest first, each deletable. Closed ones are marked.
- **The conversation itself**: what they said, what support replied, and a message from a
  person on the support team marked as such.
- **Two reasons the composer locks**, and the difference matters to the person typing.
  *Waiting on support* is temporary -- someone is deciding, and the answer will appear
  here by itself over the event stream. *Closed* is final: the issue was resolved, and
  anything new belongs in a new conversation.

## Pages

- `app/page.tsx` -- a new conversation.
- `app/c/[threadId]/page.tsx` -- one the customer already has. The address bar is updated
  with `history.replaceState` rather than a router navigation when a conversation starts,
  so beginning one does not remount the window mid-turn.
