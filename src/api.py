"""HTTP API behind the traceability dashboard.

Next.js cannot read this system on its own: conversation state lives in LangGraph
checkpoints serialized with `ormsgpack`, and resuming a paused approval means calling
`Command(resume=...)` against a compiled graph. Both are Python. So this service owns
everything that needs the agent, and the dashboard stays a view.

Three things it exposes:

- **Threads and traces** -- read straight from the `traces` table, the durable record the
  middleware writes as it decides, each thread named by what its customer wanted.
- **Live updates** -- an SSE stream that watches `MAX(traces.id)`. Polling the database
  rather than signalling in-process is deliberate: the CLI writes from a different
  process, so an in-memory event bus would never see it.
- **Approvals** -- read a thread's pending interrupt and resolve it.
- **Human replies** -- let a person answer an escalated thread in the agent's place.
- **Deletion** -- forget a thread entirely: its trace, its title, and its checkpoints.
- **Chat** -- the customer-facing surface the Support Chat app talks to. Scoped to one
  customer: it never exposes another customer's threads, which is why it is a separate
  set of routes rather than the dashboard's with a filter.
- **Status** -- open or closed. A closed thread takes no more customer messages.

Run it with `uv run api.py`.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.agents.agent import build_support_agent
from src.config import ATTENTION_FRUSTRATION, ATTENTION_WINDOW_MINUTES
from src.context import SupportContext
from src.db.database import connect, init_db, utcnow
from src.titles import delete_title, stored_titles, write_titles
from src.threads import CLOSED, OPEN, detail_of, forget, set_status, statuses
from src.trace import (
    AGENT_MESSAGE,
    HITL_DECISION,
    THREAD_CLOSED,
    current_turn,
    delete_thread_trace,
    HUMAN_AGENT_KEY,
    HUMAN_MESSAGE,
    USER_MESSAGE,
    latest_trace_id,
    record,
    thread_summaries,
    thread_trace,
)

init_db()
AGENT = build_support_agent(verbose=False)

app = FastAPI(title="Tiffin support API")

# Two front ends, and they are separate applications on purpose: the Support Dashboard
# (:3000) is internal, the Support Chat (:3001) is customer-facing. They share this
# service but not their routes -- see the chat section, which is scoped to one customer.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- threads


@app.get("/api/threads")
def list_threads() -> dict[str, Any]:
    """Every traced thread, grouped by the customer it belongs to.

    Threads are titled here rather than during a turn: the title is for whoever is
    reading the dashboard, so the customer never waits on one. Only threads that have
    never been titled cost a model call, and the answer is stored, so this settles into
    a single SELECT however often the SSE stream refreshes the list.
    """
    rows = thread_summaries()
    status = statuses(row["thread_id"] for row in rows)
    titles = stored_titles(row["thread_id"] for row in rows)
    titles.update(
        write_titles(
            [
                (row["thread_id"], row["opening_message"])
                for row in rows
                if row["thread_id"] not in titles
            ]
        )
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row["title"] = titles.get(row["thread_id"])
        row["status"] = status.get(row["thread_id"], OPEN)
        row.update(_waiting_on_a_human(row["thread_id"]))
        row["needs_attention"] = _needs_attention(row)
        row["is_live"] = _is_live(row)
        grouped[row["customer_id"]].append(row)

    customers = [
        {
            "customer_id": customer,
            "threads": threads,
            "thread_count": len(threads),
            "last_at": max(t["last_at"] for t in threads),
            "pending_approvals": sum(1 for t in threads if t["pending_approval"]),
        }
        for customer, threads in grouped.items()
    ]
    customers.sort(key=lambda c: c["last_at"], reverse=True)
    return {
        "customers": customers,
        "latest_trace_id": latest_trace_id(),
        "attention": {
            "frustration": ATTENTION_FRUSTRATION,
            "window_minutes": ATTENTION_WINDOW_MINUTES,
        },
    }


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str) -> dict[str, Any]:
    """Full decision trace for one thread, plus any approval waiting on a human."""
    events = thread_trace(thread_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No trace for thread {thread_id}")

    customer_id = events[0]["customer_id"]
    turns: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        turns[event["turn"]].append(event)

    return {
        "thread_id": thread_id,
        "customer_id": customer_id,
        "title": stored_titles([thread_id]).get(thread_id),
        "status": detail_of(thread_id),
        "events": events,
        "turns": [
            {"turn": turn, "events": items} for turn, items in sorted(turns.items())
        ],
        "pending": _pending(thread_id, customer_id),
        "state": _public_state(thread_id, customer_id),
    }


# ------------------------------------------------------------------------- approvals


class Decision(BaseModel):
    """One reviewer decision, mirroring LangChain's HITL decision shape."""

    type: Literal["approve", "reject", "edit"]
    message: str | None = None
    args: dict[str, Any] | None = Field(
        default=None, description="Replacement tool arguments, for an `edit`."
    )
    tool_name: str | None = None


class ResumeRequest(BaseModel):
    decisions: list[Decision]
    reviewer: str = "dashboard"


@app.get("/api/threads/{thread_id}/pending")
def get_pending(thread_id: str) -> dict[str, Any]:
    customer_id = _customer_of(thread_id)
    return {"pending": _pending(thread_id, customer_id)}


@app.post("/api/threads/{thread_id}/resume")
def resume_thread(thread_id: str, body: ResumeRequest) -> dict[str, Any]:
    """Resolve a paused approval and let the graph finish the turn."""
    customer_id = _customer_of(thread_id)
    pending = _pending(thread_id, customer_id)
    if pending is None:
        raise HTTPException(status_code=409, detail="No approval is pending on this thread")

    requests = pending["action_requests"]
    if len(body.decisions) != len(requests):
        raise HTTPException(
            status_code=400,
            detail=f"{len(requests)} decision(s) required, got {len(body.decisions)}",
        )

    decisions: list[dict[str, Any]] = []
    for decision, action in zip(body.decisions, requests, strict=True):
        if decision.type == "approve":
            decisions.append({"type": "approve"})
        elif decision.type == "reject":
            item: dict[str, Any] = {"type": "reject"}
            if decision.message:
                item["message"] = decision.message
            decisions.append(item)
        else:
            if not decision.args:
                raise HTTPException(status_code=400, detail="`edit` needs `args`")
            decisions.append(
                {
                    "type": "edit",
                    "edited_action": {
                        "name": decision.tool_name or action["name"],
                        "args": decision.args,
                    },
                }
            )

    for decision, action in zip(body.decisions, requests, strict=True):
        record(
            HITL_DECISION,
            f"{action['name']}: reviewer chose {decision.type}"
            + (f" — {decision.message}" if decision.message else "")
            + (f" — {json.dumps(decision.args)}" if decision.args else ""),
            {
                "tool": action["name"],
                "decision": decision.type,
                "message": decision.message,
                "edited_args": decision.args,
                "original_args": action.get("args"),
                "reviewer": body.reviewer,
                "source": "dashboard",
            },
            customer_id=customer_id,
            thread_id=thread_id,
            turn=current_turn(thread_id),
        )

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    AGENT.invoke(
        Command(resume={"decisions": decisions}),
        config=config,
        context=SupportContext(customer_id=customer_id),
    )

    return {
        "resumed": True,
        "thread_id": thread_id,
        "pending": _pending(thread_id, customer_id),
    }


# --------------------------------------------------------------------- human replies


class ReplyRequest(BaseModel):
    """A person answering the customer in the agent's place."""

    text: str
    agent: str = "support"


@app.post("/api/threads/{thread_id}/reply")
def human_reply(thread_id: str, body: ReplyRequest) -> dict[str, Any]:
    """Write a human agent's message into the thread the model is handling.

    Escalation means the model was told to hand this conversation over, and this is the
    other half of that: the reply goes into the same checkpoint the agent reads, as an
    `AIMessage` tagged with `HUMAN_AGENT_KEY`. The customer sees support answering, the
    model sees what was already promised on the next turn and does not repeat or
    contradict it, and the trace still shows which of the two said it.

    The model is deliberately not invoked. A person taking over is the point, so this
    appends to the transcript and stops there.

    The dashboard only offers this on an escalated thread, but the rule enforced here is
    narrower: no reply while an approval is pending, because resolving that interrupt
    resumes the graph, and a state update racing the resume would be written against a
    checkpoint that is about to move.
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="An empty reply has nothing to send")

    customer_id = _customer_of(thread_id)
    if _pending(thread_id, customer_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="Resolve the pending approval before replying on this thread",
        )

    author = body.agent.strip() or "support"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        AGENT.update_state(
            config,
            {
                "messages": [
                    AIMessage(
                        content=text,
                        name=_message_name(author),
                        additional_kwargs={HUMAN_AGENT_KEY: author},
                    )
                ]
            },
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the reviewer, not swallowed
        raise HTTPException(status_code=409, detail=f"Could not write the reply: {exc}")

    record(
        HUMAN_MESSAGE,
        text,
        {"text": text, "agent": author, "source": "dashboard"},
        customer_id=customer_id,
        thread_id=thread_id,
        turn=current_turn(thread_id),
    )

    return {"sent": True, "thread_id": thread_id, "agent": author}



# ----------------------------------------------------------------------------- chat


class ChatRequest(BaseModel):
    """One customer turn, from the web chat."""

    customer_id: str
    message: str
    thread_id: str | None = Field(
        default=None, description="Omit to start a new thread."
    )


@app.get("/api/customers")
def list_customers() -> dict[str, Any]:
    """Who you can sign in as. Seeded fixtures, in ID order."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT customer_id, COUNT(*) AS orders FROM orders"
            " GROUP BY customer_id ORDER BY customer_id"
        ).fetchall()
    finally:
        conn.close()
    return {"customers": [dict(r) for r in rows]}


@app.get("/api/customers/{customer_id}/threads")
def customer_threads(customer_id: str) -> dict[str, Any]:
    """One customer's own conversations, newest first, for the chat's history pane.

    Customer-scoped by construction rather than by filtering the dashboard's list: the
    chat is a different application with a different audience, and it should not be able
    to ask for rows it is not allowed to show.
    """
    rows = [r for r in thread_summaries() if r["customer_id"] == customer_id]
    status = statuses(r["thread_id"] for r in rows)
    titles = stored_titles(r["thread_id"] for r in rows)
    return {
        "customer_id": customer_id,
        "threads": [
            {
                "thread_id": r["thread_id"],
                "title": titles.get(r["thread_id"]),
                "opening_message": r["opening_message"],
                "last_at": r["last_at"],
                "turns": r["turns"],
                "status": status.get(r["thread_id"], OPEN),
            }
            for r in rows
        ],
    }


@app.get("/api/chat/{thread_id}")
def get_chat(thread_id: str) -> dict[str, Any]:
    """The conversation as the customer sees it, plus anything blocking it."""
    customer_id = _customer_of(thread_id)
    return {
        "thread_id": thread_id,
        "customer_id": customer_id,
        "messages": _transcript(thread_id),
        "pending": _pending(thread_id, customer_id),
        "status": detail_of(thread_id),
    }


@app.delete("/api/chat/{thread_id}")
def delete_own_thread(thread_id: str, customer_id: str) -> dict[str, Any]:
    """A customer deleting one of their own conversations.

    The same deletion the dashboard does, with ownership checked: the chat app may only
    remove threads belonging to the customer using it.
    """
    owner = _customer_of(thread_id)
    if owner != customer_id:
        raise HTTPException(status_code=403, detail="That is not your conversation")
    return delete_thread(thread_id)


@app.post("/api/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    """Run one customer turn and return the conversation after it.

    The CLI's `run_turn` blocks on an approval until the dashboard resolves it. This
    cannot: an HTTP request that waits on a human is a request that times out. So a turn
    that interrupts returns with `pending` set and the transcript as far as it got --
    the approval is resolved on the thread's page, and the answer lands in this
    conversation when the graph finishes.
    """
    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="An empty message has nothing to say")

    thread_id = body.thread_id or f"thread-{uuid.uuid4().hex[:8]}"
    if body.thread_id:
        # Never let one customer's session continue another's thread: the context is what
        # the tools authorize against, and the transcript is already under that customer.
        owner = _customer_of(thread_id)
        if owner != body.customer_id:
            raise HTTPException(
                status_code=403, detail=f"Thread {thread_id} belongs to {owner}"
            )

    if _pending(thread_id, body.customer_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="This thread is paused on an approval. Resolve it before writing again.",
        )

    if body.thread_id and detail_of(thread_id)["status"] == CLOSED:
        raise HTTPException(
            status_code=409,
            detail="This conversation is closed. Start a new one for anything else.",
        )

    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    try:
        AGENT.invoke(
            {"messages": [{"role": "user", "content": text}]},
            config=config,
            context=SupportContext(customer_id=body.customer_id, channel="web"),
        )
    except Exception as exc:  # noqa: BLE001 - one bad turn should not kill the session
        raise HTTPException(status_code=500, detail=f"The turn failed: {exc}")

    return {
        "thread_id": thread_id,
        "customer_id": body.customer_id,
        "messages": _transcript(thread_id),
        "pending": _pending(thread_id, body.customer_id),
        "status": detail_of(thread_id),
    }


_CHAT_EVENTS = {
    USER_MESSAGE: "customer",
    AGENT_MESSAGE: "agent",
    HUMAN_MESSAGE: "human",
}


def _transcript(thread_id: str) -> list[dict[str, Any]]:
    """What was actually said, in order, for the chat window.

    Read from the trace rather than the checkpoint, and that is not an optimization.
    `SummarizationMiddleware` rewrites the checkpoint's transcript once it passes the
    token budget: the customer's own words are replaced by a summary written *about*
    them, which a chat window would then render as something the customer said. The trace
    is append-only, so it still holds the turn as it happened.

    Tool calls, policy verdicts and Jev scores are in that same trace and are deliberately
    left out here. The customer's view and the decision record being two different things
    is the point of the whole app.
    """
    out: list[dict[str, Any]] = []
    for event in thread_trace(thread_id):
        role = _CHAT_EVENTS.get(event["event_type"])
        if role is None:
            continue
        detail = event.get("detail") or {}
        text = detail.get("text") or event["summary"]
        out.append(
            {
                "role": role,
                "text": text,
                "author": detail.get("agent") if role == "human" else None,
            }
        )
    return out


# -------------------------------------------------------------------------- status


class CloseRequest(BaseModel):
    by: str = "support"
    reason: str | None = None


@app.post("/api/threads/{thread_id}/close")
def close_thread(thread_id: str, body: CloseRequest) -> dict[str, Any]:
    """Mark a thread resolved. The customer's composer locks; the queue lets it go."""
    customer_id = _customer_of(thread_id)
    set_status(thread_id, CLOSED, by=body.by, reason=body.reason)
    record(
        THREAD_CLOSED,
        f"Closed by {body.by}" + (f" — {body.reason}" if body.reason else ""),
        {"closed_by": body.by, "reason": body.reason, "source": "dashboard"},
        customer_id=customer_id, thread_id=thread_id, turn=current_turn(thread_id),
    )
    return {"thread_id": thread_id, "status": detail_of(thread_id)}


@app.post("/api/threads/{thread_id}/reopen")
def reopen_thread(thread_id: str, body: CloseRequest) -> dict[str, Any]:
    """Put a closed thread back in play, for when it was closed too early."""
    customer_id = _customer_of(thread_id)
    set_status(thread_id, OPEN, by=body.by)
    record(
        THREAD_CLOSED,
        f"Reopened by {body.by}",
        {"closed_by": None, "reason": body.reason, "source": "dashboard",
         "reopened": True},
        customer_id=customer_id, thread_id=thread_id, turn=current_turn(thread_id),
    )
    return {"thread_id": thread_id, "status": detail_of(thread_id)}


# ------------------------------------------------------------------------ deletion


@app.delete("/api/threads/{thread_id}")
def delete_thread(thread_id: str) -> dict[str, Any]:
    """Forget a thread completely: its trace, its title, and its checkpoints.

    All three, or the thread comes back half alive -- a deleted trace with a live
    checkpoint still answers `--thread <id>` with its full history, and a deleted
    checkpoint with a live trace leaves a row in the dashboard that opens onto nothing.

    There is no undo. The caller confirms; this just does it.
    """
    _customer_of(thread_id)  # 404s if nothing was ever traced under this ID

    events = delete_thread_trace(thread_id)
    delete_title(thread_id)
    forget(thread_id)

    checkpointer = getattr(AGENT, "checkpointer", None)
    try:
        if checkpointer is not None:
            checkpointer.delete_thread(thread_id)
    except Exception as exc:  # noqa: BLE001 - the trace is already gone; say what failed
        raise HTTPException(
            status_code=500,
            detail=f"Trace deleted, but the checkpoint did not: {exc}",
        )

    return {"deleted": True, "thread_id": thread_id, "events": events}


# ------------------------------------------------------------------------------ SSE


@app.get("/api/events")
async def events() -> StreamingResponse:
    """Server-sent events: one `trace` message whenever new rows are written.

    The CLI and this service are separate processes writing the same SQLite file, so the
    only reliable change signal is the database itself.
    """

    async def stream():
        last = latest_trace_id()
        yield f"event: hello\ndata: {json.dumps({'latest_trace_id': last})}\n\n"
        while True:
            await asyncio.sleep(0.6)
            try:
                current = await asyncio.to_thread(latest_trace_id)
            except Exception:  # noqa: BLE001 - a locked DB should not kill the stream
                continue
            if current != last:
                last = current
                payload = {"latest_trace_id": current, "threads": _recent_threads(current)}
                yield f"event: trace\ndata: {json.dumps(payload)}\n\n"
            else:
                # Keep proxies and browsers from closing an idle connection.
                yield ": keepalive\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -------------------------------------------------------------------------- helpers


def _waiting_on_a_human(thread_id: str) -> dict[str, Any]:
    """The two ways a thread can be stuck waiting for a person, from one snapshot read.

    An approval is unambiguous: the graph is suspended and nothing moves until someone
    decides. An escalation is softer -- the agent has handed off and told the customer so,
    but the transcript is the only record of whether anyone actually picked it up, which
    is what `awaiting_human` reads.

    Both come off a single `get_state`, because walking the checkpoint twice per row is
    the one thing that makes listing threads slow.
    """
    blank = {
        "pending_approval": False,
        "pending_tool": None,
        "escalation_required": False,
        "awaiting_human": False,
    }
    try:
        snapshot = _snapshot(thread_id)
    except Exception:  # noqa: BLE001 - thread may predate the checkpointer
        return blank

    pending = None
    for interrupt in snapshot.interrupts or ():
        value = interrupt.value
        if isinstance(value, dict) and "action_requests" in value:
            pending = value
            break

    values = snapshot.values or {}
    escalated = bool(values.get("escalation_required"))

    return {
        "pending_approval": pending is not None,
        "pending_tool": (
            pending["action_requests"][0]["name"]
            if pending and pending.get("action_requests")
            else None
        ),
        "escalation_required": escalated,
        "awaiting_human": escalated and not _answered_by_a_human(values),
    }


def _answered_by_a_human(values: dict[str, Any]) -> bool:
    """Has a person replied since the customer last wrote?

    Anything earlier does not count: the customer has spoken again, so whatever was said
    before was about a different question.
    """
    for message in reversed(values.get("messages", [])):
        if isinstance(message, HumanMessage):
            return False
        if (getattr(message, "additional_kwargs", None) or {}).get(HUMAN_AGENT_KEY):
            return True
    return False


def _needs_attention(row: dict[str, Any]) -> bool:
    """Is this thread worth looking at before it turns into an escalation?

    Frustration over the threshold, and that is the whole rule. Recency decides how the
    card is marked, not whether it appears: a thread that went badly and then went quiet
    is still a customer who was left unhappy, and hiding it would mean the list empties
    itself out exactly when nothing is happening.
    """
    if row.get("status") == CLOSED:
        return False
    series = row.get("frustration_series") or []
    return bool(series) and series[-1] > ATTENTION_FRUSTRATION


def _is_live(row: dict[str, Any]) -> bool:
    """Has this thread moved recently enough to still be in play?"""
    try:
        last = datetime.fromisoformat(str(row["last_at"]))
    except (KeyError, TypeError, ValueError):
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return utcnow() - last <= timedelta(minutes=ATTENTION_WINDOW_MINUTES)


def _message_name(author: str) -> str:
    """`AIMessage.name` has to look like an identifier to the chat APIs."""
    cleaned = "".join(c if c.isalnum() or c in "_-" else "_" for c in author)
    return cleaned[:60] or "support"


def _customer_of(thread_id: str) -> str:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT customer_id FROM traces WHERE thread_id = ? ORDER BY id DESC LIMIT 1",
            (thread_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown thread {thread_id}")
    return row["customer_id"]


def _recent_threads(latest_id: int) -> list[str]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT thread_id FROM traces WHERE id > ?", (latest_id - 25,)
        ).fetchall()
    finally:
        conn.close()
    return [r["thread_id"] for r in rows]


def _snapshot(thread_id: str):
    return AGENT.get_state({"configurable": {"thread_id": thread_id}})


def _pending(thread_id: str, customer_id: str) -> dict[str, Any] | None:
    """The approval this thread is paused on, if any, in dashboard-ready shape."""
    try:
        snapshot = _snapshot(thread_id)
    except Exception:  # noqa: BLE001 - thread may predate the checkpointer
        return None

    for interrupt in snapshot.interrupts or ():
        value = interrupt.value
        if isinstance(value, dict) and "action_requests" in value:
            return {
                "interrupt_id": getattr(interrupt, "id", None),
                "action_requests": value["action_requests"],
                "review_configs": value.get("review_configs", []),
            }
    return None


def _public_state(thread_id: str, customer_id: str) -> dict[str, Any]:
    """The bits of agent state worth showing next to the trace."""
    try:
        values = _snapshot(thread_id).values or {}
    except Exception:  # noqa: BLE001
        return {}
    return {
        "triage": values.get("triage"),
        "frustration_history": values.get("frustration_history", []),
        "frustration_sustained": values.get("frustration_sustained", False),
        "escalation_required": values.get("escalation_required", False),
        "escalation_note": values.get("escalation_note", ""),
        "cancel_unlocked_order": values.get("cancel_unlocked_order") or None,
        "message_count": len(values.get("messages", [])),
    }
