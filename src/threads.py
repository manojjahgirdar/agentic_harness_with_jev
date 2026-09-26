"""Whether a conversation is still open.

A support thread ends. Either the agent resolved what the customer asked, or a person on
the support side decided it was done -- and once it is done the customer should not be
typing into it, and the queue should not be showing it as live work.

Kept out of the LangGraph checkpoint on purpose. Closing is something *about* the
conversation rather than something in it: the dashboard closes threads the agent never
resumes, and a row in `thread_status` can be read for a hundred threads in one query,
which loading a hundred checkpoints could not.
"""

from __future__ import annotations

import sys
from typing import Iterable, Literal

from src.db.database import connect, iso, utcnow

Status = Literal["open", "closed"]

OPEN: Status = "open"
CLOSED: Status = "closed"


def status_of(thread_id: str) -> Status:
    """One thread's status. Anything never recorded is open."""
    return statuses([thread_id]).get(thread_id, OPEN)


def statuses(thread_ids: Iterable[str]) -> dict[str, Status]:
    """Statuses for many threads at once, for the dashboard's list."""
    ids = list(thread_ids)
    if not ids:
        return {}
    try:
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT thread_id, status FROM thread_status WHERE thread_id IN "
                f"({','.join('?' * len(ids))})",
                ids,
            ).fetchall()
        finally:
            conn.close()
        return {r["thread_id"]: r["status"] for r in rows}
    except Exception as exc:  # noqa: BLE001 - an unreadable status must not hide a thread
        print(f"  [threads] could not read statuses: {exc}", file=sys.stderr)
        return {}


def set_status(
    thread_id: str, status: Status, *, by: str, reason: str | None = None
) -> None:
    """Close or reopen a thread. Raises: the caller is told whether it took."""
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO thread_status (thread_id, status, closed_by, reason, updated_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(thread_id) DO UPDATE SET"
            " status = excluded.status, closed_by = excluded.closed_by,"
            " reason = excluded.reason, updated_at = excluded.updated_at",
            (thread_id, status, by if status == CLOSED else None,
             reason if status == CLOSED else None, iso(utcnow())),
        )
        conn.commit()
    finally:
        conn.close()


def detail_of(thread_id: str) -> dict[str, str | None]:
    """Status plus who closed it and why, for the thread page."""
    conn = connect()
    try:
        row = conn.execute(
            "SELECT status, closed_by, reason, updated_at FROM thread_status"
            " WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"status": OPEN, "closed_by": None, "reason": None, "updated_at": None}
    return dict(row)


def forget(thread_id: str) -> None:
    """Drop a deleted thread's status row."""
    try:
        conn = connect()
        try:
            conn.execute("DELETE FROM thread_status WHERE thread_id = ?", (thread_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - an orphaned status harms nothing
        print(f"  [threads] could not delete status: {exc}", file=sys.stderr)
