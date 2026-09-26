"""Decision trace: the durable record of why the agent did what it did.

The stderr lines the CLI prints are for whoever is watching at the time. This is the
version that survives: every Jev classification with its confidences, every routing
choice, every policy verdict, and every human decision, written to `harness.db` as it
happens.

Two rules hold this together:

- **Tracing never breaks the agent.** Every write is wrapped; a failure here is logged to
  stderr and swallowed. An audit log that can take down the thing it audits is worse than
  no audit log.
- **Rows are self-describing.** `summary` is a human-readable line for the timeline;
  `detail_json` carries the full structured payload. The dashboard reads plain columns
  and JSON, never LangGraph's serialized checkpoint blobs.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from langchain_core.messages import HumanMessage

from src.db.database import connect, iso, utcnow

# Event types, in the order they typically occur within a turn.
USER_MESSAGE = "user_message"
JEV_TRIAGE = "jev_triage"
ESCALATION_RULE = "escalation_rule"
SKILL_INJECTED = "skill_injected"
MODEL_ROUTE = "model_route"
JEV_RISK = "jev_risk"
POLICY = "policy"
HITL_REQUEST = "hitl_request"
HITL_DECISION = "hitl_decision"
TOOL_CALL = "tool_call"
AGENT_MESSAGE = "agent_message"
HUMAN_MESSAGE = "human_message"
THREAD_CLOSED = "thread_closed"

HUMAN_AGENT_KEY = "human_agent"
"""`additional_kwargs` marker distinguishing a person's reply from the model's.

A human agent's reply is written into the transcript as an `AIMessage`, because to the
customer -- and to the model reading the history back on the next turn -- it is simply
what support said. This key is what still tells the two apart afterwards.
"""


def current_thread_id() -> str:
    """The thread this turn belongs to, read from the LangGraph run config."""
    try:
        from langgraph.config import get_config

        return str(get_config().get("configurable", {}).get("thread_id", "unknown"))
    except Exception:  # noqa: BLE001 - outside a graph run, or no config
        return "unknown"


def turn_of(state: Any) -> int:
    """Which customer turn this is.

    Read from state, where `JevTriageMiddleware` maintains it. The fallback counts
    HumanMessages, which is only correct before the transcript has been summarized --
    hence the stored value being authoritative.
    """
    try:
        if isinstance(state, dict):
            stored = state.get("turn")
            if isinstance(stored, int) and stored > 0:
                return stored
            messages = state.get("messages", [])
            return sum(1 for m in messages if isinstance(m, HumanMessage))
    except Exception:  # noqa: BLE001
        pass
    return 0


def record(
    event_type: str,
    summary: str,
    detail: dict[str, Any] | None = None,
    *,
    customer_id: str,
    thread_id: str | None = None,
    turn: int = 0,
) -> None:
    """Append one decision to the trace. Never raises."""
    try:
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO traces (thread_id, customer_id, turn, ts, event_type,"
                " summary, detail_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    thread_id or current_thread_id(),
                    customer_id,
                    turn,
                    iso(utcnow()),
                    event_type,
                    summary,
                    json.dumps(detail or {}, default=str),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - tracing must never break a conversation
        print(f"  [trace] failed to record {event_type}: {exc}", file=sys.stderr)


def record_once(
    event_type: str,
    summary: str,
    detail: dict[str, Any] | None = None,
    *,
    customer_id: str,
    dedupe_key: str,
    thread_id: str | None = None,
    turn: int = 0,
) -> None:
    """Record an event unless an identical one already exists for this turn.

    Some hooks legitimately run more than once for a single decision -- LangGraph replays
    `after_model` when a thread resumes from an interrupt, so the approval request would
    otherwise appear twice for one pause. The dedupe key is what makes two records "the
    same decision" rather than two decisions that happen to look alike.
    """
    try:
        tid = thread_id or current_thread_id()
        conn = connect()
        try:
            existing = conn.execute(
                "SELECT 1 FROM traces WHERE thread_id = ? AND event_type = ? AND turn = ?"
                " AND json_extract(detail_json, '$._key') = ? LIMIT 1",
                (tid, event_type, turn, dedupe_key),
            ).fetchone()
        finally:
            conn.close()
        if existing:
            return
    except Exception as exc:  # noqa: BLE001
        print(f"  [trace] dedupe check failed for {event_type}: {exc}", file=sys.stderr)

    record(
        event_type,
        summary,
        {**(detail or {}), "_key": dedupe_key},
        customer_id=customer_id,
        thread_id=thread_id,
        turn=turn,
    )


def thread_summaries() -> list[dict[str, Any]]:
    """One row per thread, newest activity first, for the dashboard's sidebar."""
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT
                t.thread_id,
                t.customer_id,
                COUNT(*)                                        AS events,
                MAX(t.turn)                                     AS turns,
                MIN(t.ts)                                       AS started_at,
                MAX(t.ts)                                       AS last_at,
                MAX(t.id)                                       AS last_id,
                (SELECT summary FROM traces u
                  WHERE u.thread_id = t.thread_id AND u.event_type = ?
                  ORDER BY u.id LIMIT 1)                        AS opening_message,
                (SELECT json_extract(j.detail_json, '$.category') FROM traces j
                  WHERE j.thread_id = t.thread_id AND j.event_type = ?
                  ORDER BY j.id DESC LIMIT 1)                   AS latest_category,
                (SELECT json_extract(f.detail_json, '$.frustration') FROM traces f
                  WHERE f.thread_id = t.thread_id AND f.event_type = ?
                  ORDER BY f.id DESC LIMIT 1)                   AS latest_frustration,
                (SELECT COUNT(*) FROM traces e
                  WHERE e.thread_id = t.thread_id
                    AND ((e.event_type = ?
                          AND json_extract(e.detail_json, '$.escalated') = 1)
                      OR (e.event_type = 'tool_call'
                          AND json_extract(e.detail_json, '$.tool') = 'escalate_to_human'
                          AND json_extract(e.detail_json, '$.status') != 'error')))
                                                                    AS escalations,
                (SELECT COUNT(*) FROM traces h
                  WHERE h.thread_id = t.thread_id AND h.event_type = ?)  AS approvals
            FROM traces t
            GROUP BY t.thread_id, t.customer_id
            ORDER BY MAX(t.id) DESC
            """,
            (USER_MESSAGE, JEV_TRIAGE, JEV_TRIAGE, ESCALATION_RULE, HITL_REQUEST),
        ).fetchall()
    finally:
        conn.close()

    series = _frustration_series()
    return [{**dict(r), "frustration_series": series.get(r["thread_id"], [])} for r in rows]


def _frustration_series() -> dict[str, list[float]]:
    """Every frustration score Jev has given, per thread, oldest first.

    `latest_frustration` says where a customer ended up; the list says how they got
    there, which is the difference between one bad moment and a conversation going
    wrong. Read in one query and zipped in Python rather than aggregated in SQL, because
    `json_group_array` does not promise to respect a subquery's ordering.
    """
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT thread_id, json_extract(detail_json, '$.frustration') AS frustration"
            " FROM traces WHERE event_type = ? ORDER BY id",
            (JEV_TRIAGE,),
        ).fetchall()
    finally:
        conn.close()

    series: dict[str, list[float]] = {}
    for row in rows:
        if row["frustration"] is None:
            continue
        series.setdefault(row["thread_id"], []).append(float(row["frustration"]))
    return series


def thread_trace(thread_id: str) -> list[dict[str, Any]]:
    """Every recorded decision for one thread, in the order it happened."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, thread_id, customer_id, turn, ts, event_type, summary,"
            " detail_json FROM traces WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
    finally:
        conn.close()

    out = []
    for r in rows:
        item = dict(r)
        try:
            item["detail"] = json.loads(item.pop("detail_json"))
        except (TypeError, ValueError):
            item["detail"] = {}
        out.append(item)
    return out


def current_turn(thread_id: str) -> int:
    """The turn this thread has reached, for callers outside the graph.

    Middleware reads the turn from state; a tool called through the graph, or the API
    recording a reviewer's decision, has no state to read and asks the trace instead.
    """
    try:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(turn), 0) FROM traces WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        finally:
            conn.close()
        return int(row[0])
    except Exception:  # noqa: BLE001 - turn 0 is a safe answer
        return 0


def delete_thread_trace(thread_id: str) -> int:
    """Drop every traced decision for one thread. Returns how many rows went.

    Unlike `record`, this is allowed to raise: a delete that half worked and said nothing
    would leave the dashboard showing a thread the caller believes is gone.
    """
    conn = connect()
    try:
        cursor = conn.execute("DELETE FROM traces WHERE thread_id = ?", (thread_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def latest_trace_id() -> int:
    """Highest trace id, used by the SSE stream to detect new activity."""
    conn = connect()
    try:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM traces").fetchone()
    finally:
        conn.close()
    return int(row[0])
