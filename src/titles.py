"""Names a thread by what the customer wanted, so the dashboard can stop showing UUIDs.

`thread-e14322e9` says nothing about the conversation it identifies. This writes a short
intent summary once per thread and stores it in `thread_titles`, keyed by thread, so the
cost is paid a single time and every later read is a SELECT.

Two things keep it out of the way of the actual work:

- **It runs on the dashboard's side, not the customer's.** Titling is a reading
  convenience, so the fast model is called when threads are listed, never during a turn.
  Nobody waits on a title.
- **It never raises.** A model that is down, slow, or returning nonsense costs the
  dashboard its titles and nothing else; the caller falls back to the opening message.
"""

from __future__ import annotations

import sys
from typing import Iterable

from src.config import TITLE_BATCH_LIMIT, TITLE_MAX_WORDS
from src.db.database import connect, iso, utcnow
from src.models.openai import TITLER

_PROMPT = (
    "Summarize what this customer wants, as a label for their support thread.\n"
    f"At most {TITLE_MAX_WORDS} words. No quotes, no final period, no customer name.\n"
    "Name the thing and the problem, e.g. 'Missing edamame from ORD-1003' or\n"
    "'Late order, wants it cancelled'.\n\n"
    "Customer's message:\n{message}"
)

_MAX_CHARS = 64
"""Hard cap, because a model that ignores the word limit should not break the layout."""


def stored_titles(thread_ids: Iterable[str]) -> dict[str, str]:
    """Titles already written, for the threads asked about."""
    ids = list(thread_ids)
    if not ids:
        return {}
    try:
        conn = connect()
        try:
            rows = conn.execute(
                "SELECT thread_id, title FROM thread_titles WHERE thread_id IN "
                f"({','.join('?' * len(ids))})",
                ids,
            ).fetchall()
        finally:
            conn.close()
        return {r["thread_id"]: r["title"] for r in rows}
    except Exception as exc:  # noqa: BLE001 - a missing title is not an error
        print(f"  [titles] could not read titles: {exc}", file=sys.stderr)
        return {}


def write_titles(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """Title each `(thread_id, opening_message)` with the fast model, and store them.

    Batched so a first load with a dozen untitled threads is one round of concurrent
    calls rather than a dozen sequential ones, and capped so it can never be more than
    one round.
    """
    batch = [(tid, text) for tid, text in pairs if text and text.strip()]
    batch = batch[:TITLE_BATCH_LIMIT]
    if not batch:
        return {}

    try:
        replies = TITLER.batch(
            [_PROMPT.format(message=text[:600]) for _, text in batch]
        )
    except Exception as exc:  # noqa: BLE001 - fall back to showing the opening message
        print(f"  [titles] model call failed: {exc}", file=sys.stderr)
        return {}

    written: dict[str, str] = {}
    for (thread_id, _), reply in zip(batch, replies, strict=True):
        title = _clean(getattr(reply, "text", "") or "")
        if not title:
            continue
        written[thread_id] = title

    _store(written)
    return written


def delete_title(thread_id: str) -> None:
    """Forget a thread's title, so a reused ID is not named after an old conversation."""
    try:
        conn = connect()
        try:
            conn.execute("DELETE FROM thread_titles WHERE thread_id = ?", (thread_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - an orphaned title harms nothing
        print(f"  [titles] could not delete title: {exc}", file=sys.stderr)


def _clean(raw: str) -> str:
    """Trim the model's answer down to something that fits a sidebar row."""
    title = " ".join(raw.strip().split())
    title = title.strip("\"'").rstrip(".")
    words = title.split(" ")
    if len(words) > TITLE_MAX_WORDS:
        title = " ".join(words[:TITLE_MAX_WORDS])
    return title[:_MAX_CHARS].strip()


def _store(titles: dict[str, str]) -> None:
    if not titles:
        return
    now = iso(utcnow())
    try:
        conn = connect()
        try:
            conn.executemany(
                "INSERT OR REPLACE INTO thread_titles (thread_id, title, created_at)"
                " VALUES (?, ?, ?)",
                [(tid, title, now) for tid, title in titles.items()],
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        print(f"  [titles] could not store titles: {exc}", file=sys.stderr)
