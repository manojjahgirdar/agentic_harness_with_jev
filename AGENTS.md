# Agents.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Check the LangChain docs before scaffolding

Before writing any new LangChain code in this repo — filling in an empty `src/` module, adding an
agent, tool, middleware, memory/checkpointer, or prompt-loading layer, or changing how a model is
initialized — consult the `docs-langchain` MCP server first. Do not write LangChain APIs from
memory: this project is on LangChain 1.x, where `create_agent` replaced the older
`AgentExecutor`/`initialize_agent` surface and middleware and memory have their own current
contracts, so recalled patterns are likely to be a version behind.

- `mcp__docs-langchain__search_docs_by_lang_chain` — semantic search; returns page paths.
- `mcp__docs-langchain__query_docs_filesystem_docs_by_lang_chain` — read-only sandbox shell over the
  docs. Read a page by appending `.mdx` to a search result's path (`cat /some/page.mdx`); use
  `tree / -L 2` or `rg -il "keyword" /` to find paths rather than guessing them.

Prefer what the docs return over prior knowledge, and cite the page path in the explanation of any
non-obvious API choice so the next reader can check it. The server only covers the published docs;
it is not a substitute for reading `langchain-typesafe`, which is alpha and may not be documented
there.

## Status

A working CLI support agent for a fictional food delivery company ("Tiffin"). `uv run
main.py` starts a chat loop; `src/cli.py` is the only front end, and the future UI is
expected to replace it by calling `run_turn` with the same interrupt/resume protocol.

## Commands

The project is managed with `uv` (Python 3.13 pinned via `.python-version`):

```bash
uv sync                                  # install/refresh the venv from uv.lock
uv run main.py                           # chat as cust-1
uv run main.py --customer cust-7         # the seeded refund abuser
uv run main.py --thread thread-abc123    # resume a stored thread
uv run main.py --reseed                  # reset demo orders/refunds (not checkpoints)
uv add <pkg>                             # add a dependency
```

No lint, format, or test commands are configured, and `tests/` is empty.

Note that `--reseed` clears the business tables only. LangGraph checkpoints persist, so a
reused `--thread` still carries its old transcript; use a fresh thread for a clean run.

## Architecture

One customer message flows through the stack in `src/middleware/__init__.py`, in order:

1. **`JevTriageMiddleware`** (`before_model`) — one `TypeSafeClassifier` call per customer
   turn (skipped on tool-loop iterations) producing a `Choice` category, an urgency
   `Noul`, a frustration `Score`, and a `needs_reasoning` `Noul`. Also applies the
   escalation rule sets `escalation_required` in state only when a human can do what the
   agent cannot: the customer asked for one, it is legal or safety, or frustration kept
   building *and* nothing is left to try.
2. **`SummarizationMiddleware`** — compacts the transcript past `SUMMARIZE_AFTER_TOKENS`.
3. **`support_prompt`** (`dynamic_prompt`) — composes the system message from
   `prompts/system_prompt.md` + `prompts/soul.md` + a triage block + the one `SKILL.md`
   matching the Jev category + any escalation directive. There is no `load_skill` tool and
   no `system_prompt=` on `create_agent`; the category picks the skill.
4. **`ModelRouterMiddleware`** (`wrap_model_call`) — `request.override(model=...)` between
   the fast and reasoning models. `choose_model` is pure and directly testable.
5. **the risk gate** (`HumanInTheLoopMiddleware`) — its `when` predicate combines
   `policy.evaluate_refund` with a Jev `Score` over the proposed call and the recent
   transcript. Firing interrupts the graph; the CLI prompts approve/edit/reject and
   resumes with `Command(resume={"decisions": [...]})`.
6. **`RefundPolicyMiddleware`** (`wrap_tool_call`) — hard refusal for abuse patterns and
   the absolute ceiling, for both money-moving tools (`issue_refund`, `cancel_order`).

### The remedy ladder

What a late order is owed depends on how far it got, because that determines whether the
money still exists. `db.fulfilment_stage` collapses `status` + `courier` + `delivered_at`
into the only distinction that matters:

| stage | cancel? | refund | why |
|---|---|---|---|
| `placed`, `preparing` | yes | full | nothing cooked, nothing spent |
| `awaiting_courier` | only after a failed remedy | full | cooked, but nobody is carrying it |
| `with_courier` | **never** | $0 | cooked and in motion; cancelling returns nothing |
| `delivered` | no | — | `issue_refund` territory |

The three money tools have deliberately different gates:

- `issue_refund` — discretionary. Risk gate; pauses above `REFUND_AUTO_MAX`.
- `issue_voucher` — **always** pauses. Deciding what someone's goodwill is worth is the
  human's call, and that pause *is* the remedy step. Capped by `VOUCHER_MAX_AMOUNT`, one
  per order (`VOUCHER_ONE_PER_ORDER`) so renewed anger cannot be answered with the same
  offer twice.
- `cancel_order` — never approved, only *permitted* by the stage ladder, which already
  refuses every case a human would have refused.

`frustration_sustained` is the release valve, set in `JevTriageMiddleware` from the
per-turn frustration `Score` kept in `frustration_history`. It trips on two upset turns
**or** on frustration still climbing across turns (`FRUSTRATION_RISE_FOR_CANCEL`) — the
second matters more, because a customer who got angrier *after* the voucher has told you
the remedy failed. When it trips on an `awaiting_courier` order, `cancel_unlocked_order`
is set and no escalation is required, the prompt says "settle this yourself" -- the agent
finishes a case it is now allowed to close rather than queueing it behind a human. With
both set, the prompt says "settle, then escalate", and cancelling
becomes permitted. It never unlocks `with_courier`.

**Anything that reads a policy decision must read it from the same inputs.** Two bugs in
this file's history were both the same shape: the guard and the payout evaluating the same
rule on different inputs. `cancel_order` therefore reads `frustration_sustained` from
`runtime.state` rather than recomputing without it.

**Middleware 5 and 6 must stay in that order.** `wrap_tool_call` layers compose
outermost-first, and HITL substitutes a reviewer's edited arguments inside its own
`wrap_tool_call`. With the policy check outside it, policy would judge the amount the
model proposed while the tool executed the amount the reviewer typed.

Every threshold lives in `src/config.py`. Refund rules live once in `src/policy.py` and
are called from both the risk gate and the policy middleware so the two cannot drift.

`src/context.py` holds `SupportContext`, passed as the `context=` kwarg to `invoke` (not a
config key) and read as `runtime.context` in middleware and `ToolRuntime` in tools. The
customer ID comes from there, never from model output.

`src/models/` keeps the established convention: `init_chat_model(...)` assigned to an
uppercase module constant. `FAST_MODEL` is `openai:gpt-5.5` — `gpt-5.5-fast` 404s on this
account.

`langchain-typesafe` (`0.0.1a3`, alpha) supplies `TypeSafeClassifier` with `Noul`,
`Choice`, and `Score` questions; results come back as `response.nouls[...]`,
`response.choices[...]` (with `.confidence`), and `response.scores[...]` (an expected
value over the rubric, so fractional scores are normal).

## Traceability

`src/trace.py` writes every decision to a `traces` table as it is made: Jev scores with
their confidences, model routing, policy verdicts, approval requests and how they were
resolved, tool calls, and both sides of the conversation. The stderr lines are for
whoever is watching; this is the version that survives.

Two invariants. Tracing never raises -- a failed write is printed and swallowed, because
an audit log that can break the thing it audits is worse than none. And rows are
self-describing: `summary` for the timeline, `detail_json` for the structured payload, so
the dashboard never touches LangGraph's `ormsgpack` checkpoint blobs.

`record_once` exists because some hooks legitimately run twice for one decision --
LangGraph replays `after_model` when a thread resumes, which would otherwise log one
approval pause as two.

**Turn numbers are stored in state, not derived.** Counting `HumanMessage`s looks correct
until `SummarizationMiddleware` compacts them away, after which later events in a turn get
filed under an earlier one.

`src/titles.py` names a thread by the customer's opening message, using the fast model,
and stores the answer in `thread_titles`. It runs from `list_threads`, not from a
middleware, on purpose: a title is for whoever is reading the dashboard, so it must not
sit on the conversation's critical path. Only untitled threads cost a call, `.batch()`
makes a first load one concurrent round rather than a dozen sequential ones,
`TITLE_BATCH_LIMIT` caps that round, and every failure path falls back to showing the
opening message. Like tracing, it never raises.

`src/api.py` (`uv run api.py`) serves the dashboard: threads grouped by customer, a
thread's trace, an SSE stream that watches `MAX(traces.id)`, approval resume, and a human
agent's reply into an escalated thread. It polls
the database rather than signalling in-process because the CLI writes from a different
process. It exists at all because conversation state is `ormsgpack`-serialized and
resuming needs `Command(resume=...)` against a compiled graph -- both Python-only.

The two front ends are separate applications, and the API's routes are split to match.
`/api/threads/*` is the Support Dashboard's: every thread, every decision, approvals,
deletion. `/api/chat/*` and `/api/customers/{id}/threads` are the Support Chat's, scoped
to one customer and returning nothing about how a decision was made. A customer-facing app
that *could* request another customer's trace is one refactor away from doing it, so it
cannot.

Only one process may resolve a given interrupt, so the CLI never prompts -- it always
defers to the dashboard. It waits for the interrupt to clear *and* for `snapshot.next` to
be empty, since the interrupt clears the moment the other process starts resuming, while
the model is still working.

`DELETE /api/threads/{id}` removes all three homes a thread has: its `traces` rows, its
`thread_titles` row, and its LangGraph checkpoints (`SqliteSaver.delete_thread`). Anything
less leaves it half alive -- a deleted trace with a live checkpoint still answers
`--thread <id>` with the full history, and a deleted checkpoint with a live trace leaves a
dashboard row that opens onto nothing. `delete_thread_trace` is the one function in
`trace.py` allowed to raise: a delete that half worked and said nothing is worse than a
loud failure.

`src/threads.py` holds whether a conversation is still open, in `thread_status`. It is
deliberately not in the checkpoint: closing is something *about* a conversation rather
than something in it -- the dashboard closes threads the agent never resumes -- and one
query answers for a hundred threads where a hundred checkpoint loads would not. The agent
closes a thread with the `close_conversation` tool; a person closes it with
`POST /api/threads/{id}/close`. A closed thread refuses new customer messages (409) and
drops out of the watchlist.

`POST /api/chat` is the web front end's turn: it invokes the agent once and returns,
where `run_turn` in the CLI blocks until an approval is resolved. An HTTP request cannot
wait on a human, so a turn that interrupts comes back with `pending` set and the answer
lands later, when the resume finishes the graph. It refuses a `thread_id` belonging to
another customer -- the context is what tools authorize against and must never come from
the conversation.

`_transcript` reads the chat from the *trace*, not the checkpoint, and that is not an
optimization: `SummarizationMiddleware` rewrites the checkpoint's messages once the
transcript passes the token budget, replacing the customer's own words with a summary
written about them, which a chat window would then render as something the customer said.
The trace is append-only.

`_waiting_on_a_human` reads both blocked states off one `get_state` per thread --
`pending_approval` from the interrupt, `awaiting_human` from `escalation_required` plus a
walk back through the transcript for a `HUMAN_AGENT_KEY` message newer than the last
`HumanMessage`. One snapshot, because walking the checkpoint twice per row is what makes
listing threads slow. The transcript is the only record of whether an escalation was
picked up: nothing else writes that down.

`needs_attention` is the watchlist rule from `src/config.py`: frustration past
`ATTENTION_FRUSTRATION`, and nothing else. `is_live` (activity inside
`ATTENTION_WINDOW_MINUTES`) sorts and marks those cards but does not filter them -- an
earlier version required both, and on a demo database where nothing has moved for an hour
that rendered an empty section, which reads as a missing feature rather than a quiet
queue. Both are computed in the API rather than the browser so the thresholds stay with
the other policy knobs.

`POST /api/threads/{id}/reply` is the other direction: a person answering an escalated
thread. It appends an `AIMessage` tagged with `HUMAN_AGENT_KEY` via `update_state` and
records a `human_message` trace row, without invoking the model. An `AIMessage` rather
than a `HumanMessage` because the transcript reads role-wise, not author-wise: to the
customer and to the model on the next turn, it is what support said. It refuses while an
approval is pending -- a state write racing a `Command(resume=...)` would be applied to a
checkpoint that is about to advance.

## Environment

`src/config.py` calls `dotenv.load_dotenv()` at import and everything imports from it.
`.env` holds `OPENAI_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, and `TYPESAFE_API_KEY`;
it is now covered by `.gitignore`, as is `harness.db`.

`harness.db` holds both the LangGraph checkpoints and the fake `orders` / `order_items` /
`refunds` / `escalations` tables, seeded on first run by `src/db/database.py`.
