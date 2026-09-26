# Jev agentic harness

A customer support agent for a fictional food delivery company, built on LangChain 1.x
`create_agent`. It exists to show one thing concretely: what changes when a small,
typed classifier sits in front of the model instead of the model classifying itself.

[Jev](https://pypi.org/project/langchain-typesafe/) (`TypeSafeClassifier`) answers four
questions about every customer message, and the answers drive real control flow —
which model runs, which playbook is loaded, and whether a refund is allowed to execute.

## Run it

```bash
uv sync
uv run main.py                     # chat as cust-1
```

`.env` needs `OPENAI_API_KEY` and `TYPESAFE_API_KEY`.

```bash
uv run main.py --customer cust-7   # seeded refund abuser
uv run main.py --thread <id>       # resume a stored conversation
uv run main.py --reseed            # reset the demo orders and refunds
uv run main.py --quiet             # hide the routing/policy trace
```

In-chat: `/state` dumps the current triage, `/new` starts a fresh thread, `/quit` exits.

## What happens to a message

```
customer message
      │
      ├─ Jev triage ──── Choice: category (5 workflows)
      │                  Noul:   urgency
      │                  Score:  frustration (0 calm → 2 angry)
      │                  Noul:   needs_reasoning
      │                  + escalation rule: asked for a human, or out of moves
      │
      ├─ summarization ── compacts the thread past 3k tokens
      │
      ├─ prompt ───────── system + soul + triage + the ONE matching SKILL.md
      │
      ├─ model routing ── gpt-5.5 for lookups, gpt-6-luna for judgment calls
      │
      ├─ risk gate ────── policy thresholds + a Jev risk Score over the proposed
      │                   tool call → interrupts for human approval
      │
      └─ money policy ─── hard refusal for abuse patterns and the $200 ceiling,
                          on both issue_refund and cancel_order
```

## The five paths

| Say this as | and you get |
|---|---|
| `cust-2`: "when is my pizza getting here?" | fast model, one tool call, no guardrails |
| `cust-1`: "the edamame was missing from ORD-1003" | $9 refund, auto-approved |
| `cust-1`: "WHERE IS MY FOOD?!" | 95 min late → the agent says so and settles it itself |
| `cust-1`: "the Buddha Bowl and Edamame were missing from ORD-1003" | $25.25 → pauses for your approval |
| `cust-7`: "the korma was cold, refund me $20" | 3 refunds in 30 days → refused, escalated |
| `cust-3`: "an hour late, cancel and refund" | food cooked, no courier → $5 voucher, no refund |
| `cust-3`: then "are you serious?" | frustration climbing → cancels and refunds $30 itself |
| `cust-4`: same, but a courier has it | voucher, then a human — **never** cancels or refunds |

The last three are the interesting ones. What a late order is owed depends on how far it
got, because that decides whether the money still exists:

| fulfilment stage | cancel? | refund |
|---|---|---|
| `placed`, `preparing` | yes | full |
| `awaiting_courier` | only after a remedy failed | full |
| `with_courier` | never | $0 |
| `delivered` | no — that is `issue_refund` | — |

Once the kitchen has cooked the food, that money is spent whatever the customer decides.
Cancelling then is not a reversal, it is a second payment — so the agent offers a
voucher (which a human always approves), and cancellation unlocks only if frustration
*keeps climbing* after that. Never for an order a courier is already carrying.

## The trace dashboard

A Next.js dashboard showing every thread grouped by customer, and for each thread the
decisions behind it: which Jev question was asked, what it answered, how confident it
was, and what the harness did with that answer.

Three processes:

```bash
uv run api.py                       # :8000  support API (needs Python: checkpoints + resume)
cd dashboard && npm run dev         # :3000  Support Dashboard — internal
cd chat && npm run dev              # :3001  Support Chat — customer-facing
uv run main.py --customer cust-3    #        the same conversation in a terminal, if you prefer
```

**Two applications, on purpose.** The Support Dashboard is for the people who run this
service: every decision, the approval queue, the escalation queue, delete. The Support
Chat is what a customer sees: their own conversations and nothing else. They share the
API but not its routes -- the chat's are scoped to one customer, so the customer-facing
app cannot ask for rows it is not allowed to show. Keeping them apart is a boundary, not
a layout choice, and it is far easier to hold if they are separate apps from the start.

Decisions stream in over server-sent events, so a conversation -- in the browser at
`/chat` or in the terminal -- shows up in the trace as it happens.

**The chat is the customer's view and nothing else.** No tool calls, no policy verdicts,
no Jev scores. A turn that pauses for an approval locks the composer rather than blocking
on a human, and the reply arrives over the same event stream once someone decides it. The
customer sees their own history down the left, and can delete any of their conversations.

**A conversation ends.** The agent calls `close_conversation` when the customer's issue is
resolved, and the support team can close one from the dashboard; either way the chat's
composer locks, the thread drops out of the "needs attention" queue, and the dashboard's
table shows it as `closed`. Reopening is one click, because closing early is the easy
mistake. Closing is not deleting -- everything the thread decided stays readable, which is
the whole point of keeping a trace.

**Approvals belong to the dashboard.** Only one process may resolve a given interrupt --
whoever calls `Command(resume=...)` first advances the checkpoint -- so the CLI does not
prompt at all. When a tool call pauses, the terminal says so and waits for the browser,
then picks the conversation back up.

**An escalated thread can be answered by a person.** Where the agent hands off, the
dashboard offers a composer: what you write goes into the same transcript as support, the
CLI prints it to the customer, and the model reads it on the next turn instead of
repeating what you already promised. The model is not invoked -- the point is that a human
took over.

**Threads are listed by what was asked, not by their ID.** The fast model writes a
few-word intent summary the first time a thread is listed -- `thread-e14322e9` becomes
"Order status inquiry" -- and it is stored in `thread_titles`, so it costs one cheap call
per thread and a SELECT thereafter. Titling happens on the dashboard's side, never during
a turn, so no customer waits on one. The table shows type, that summary, the opening
query, whether it escalated, and how frustration moved across the conversation; a row
opens the full trace on its own page, and ten rows fit on one.

**What is blocked on a person comes first.** *Action required* lists the threads a human
is holding up: an approval paused mid-turn (the graph is suspended, the customer has had
no answer), and an escalation where the agent handed off and nobody has replied since the
customer last wrote. Approvals sort first, because those threads cannot move at all.

**Threads heading for trouble surface below that.** *Action maybe required soon* lists
threads whose frustration has passed `ATTENTION_FRUSTRATION` (0.50, well below the
escalation line), still-moving ones first, marked with a live dot when they have changed
inside `ATTENTION_WINDOW_MINUTES`. Recency orders the list rather than filtering it: a
thread that went badly and then went quiet is still a customer who was left unhappy, and
gating on it would empty the section out exactly when nothing is happening. A row can also
be deleted, which forgets the thread entirely: trace, title and checkpoints. There is no
undo.

What the timeline shows per turn: the customer's message, the Jev triage with a meter and
threshold marker per question, the escalation-rule outcome, which SKILL.md was injected,
which model was routed to and why, any Jev tool-risk score, each policy verdict with the
numbers behind it, approvals and how they were resolved, every tool call with arguments
and result, the reply, and anything a human agent said. "Jev decisions only" filters to just the classifier's part.

## Layout

```
src/
  config.py        every threshold, in one place
  policy.py        refund + escalation rules (pure, no LLM)
  context.py       SupportContext — the authenticated customer
  classification/  the two Jev classifiers
  middleware/      triage → prompt → routing → risk gate → refund policy
  skills/          one SKILL.md per category, injected by the classifier
  tools/           placeholder order, refund, and escalation tools
  memory/          SQLite checkpointer + summarization
  db/              schema and demo fixtures
  prompts/         system prompt and voice
  cli.py           terminal front end
  trace.py         durable decision log (the `traces` table)
  titles.py        fast-model thread titles (the `thread_titles` table)
  api.py           FastAPI service behind the dashboard
dashboard/         Next.js trace dashboard
  app/page.tsx              every thread as a table row
  app/threads/[threadId]/   one thread's trace, on its own page
```

Tools are placeholders over a seeded SQLite database (`harness.db`), which also stores
the LangGraph checkpoints — so an interrupted refund survives the process exiting.

## Notes

- Middleware order matters, and the last two entries especially: the refund policy check
  must sit *inside* the human-in-the-loop gate, or it judges the amount the model
  proposed while the tool executes the amount the reviewer typed. See
  `src/middleware/__init__.py`.
- `gpt-5.5-fast` is not a reachable model ID; the fast tier uses `gpt-5.5`.
- `langchain-typesafe` is `0.0.1a3` — alpha, and the API may move.
