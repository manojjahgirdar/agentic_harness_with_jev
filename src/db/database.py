"""SQLite access for the placeholder business data.

The same file backs the LangGraph checkpointer (see `src/memory/memory.py`), so the
whole harness is one portable `harness.db`. Tables here are deliberately fake: they
exist so the middleware has real rows to reason over.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from src.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id      TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL,
    restaurant    TEXT NOT NULL,
    status        TEXT NOT NULL,          -- see fulfilment_stage() for what each means:
                                            -- placed | preparing | awaiting_courier
                                            -- | out_for_delivery | delivered | cancelled
    total_amount  REAL NOT NULL,
    placed_at     TEXT NOT NULL,          -- ISO-8601 UTC
    promised_at   TEXT NOT NULL,
    delivered_at  TEXT,
    courier       TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   TEXT NOT NULL REFERENCES orders(order_id),
    name       TEXT NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    missing    INTEGER NOT NULL DEFAULT 0  -- set by report_missing_items
);

CREATE TABLE IF NOT EXISTS refunds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    amount      REAL NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'issued'
);

CREATE TABLE IF NOT EXISTS vouchers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,
    order_id    TEXT,
    customer_id TEXT NOT NULL,
    amount      REAL NOT NULL,
    valid_days  INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id   TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    turn        INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    summary     TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS thread_titles (
    thread_id  TEXT PRIMARY KEY,       -- what the thread is about, in a few words, so
    title      TEXT NOT NULL,          -- the dashboard can name it something other than
    created_at TEXT NOT NULL           -- its UUID. Written once, by src/titles.py.
);

CREATE TABLE IF NOT EXISTS thread_status (
    thread_id  TEXT PRIMARY KEY,
    status     TEXT NOT NULL DEFAULT 'open',   -- open | closed
    closed_by  TEXT,                           -- 'agent', or the support agent's name
    reason     TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS traces_thread ON traces(thread_id, id);
CREATE INDEX IF NOT EXISTS traces_customer ON traces(customer_id, id);

CREATE TABLE IF NOT EXISTS escalations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT,
    customer_id TEXT NOT NULL,
    reason      TEXT NOT NULL,
    priority    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    ticket_id   TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    """Open a connection with row access by column name.

    WAL mode matters here: the CLI, the API server, and the dashboard all read and write
    this file at once. Without it a reader blocks the agent mid-turn.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: datetime) -> str:
    return moment.isoformat()


def parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def fulfilment_stage(status: str, courier: str | None, delivered_at: str | None) -> str:
    """Collapse an order row into the stage that decides what cancelling it costs.

    `status` records what the operation did; this records what has been *spent*, which is
    the only thing a cancellation policy cares about:

    - `placed` / `preparing` -- nothing cooked yet, or cooking is stoppable.
    - `awaiting_courier` -- food is made and sitting on the pass. The money is gone, but
      nobody is carrying it, so the delivery can still be called off.
    - `with_courier` -- food is made and a courier has it. Cancelling returns nothing and
      strands a delivery.
    - `delivered` / `cancelled` -- terminal.
    """
    if delivered_at is not None or status == "delivered":
        return "delivered"
    if status == "cancelled":
        return "cancelled"
    if status == "out_for_delivery" or courier is not None:
        return "with_courier"
    if status == "awaiting_courier":
        return "awaiting_courier"
    if status == "preparing":
        return "preparing"
    return "placed"


def init_db(*, reseed: bool = False) -> None:
    """Create the schema and, on an empty database, load demo fixtures.

    Fixture timestamps are written relative to *now* so the "95 minutes late" order is
    still 95 minutes late whenever the demo is run.
    """
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        if reseed:
            # `traces` is deliberately absent: it is an audit log, and resetting the
            # demo fixtures should not erase the history of what the agent decided.
            for table in ("order_items", "orders", "refunds", "escalations", "vouchers"):
                conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed table names
        already_seeded = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if not already_seeded:
            _seed(conn)
        conn.commit()
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    now = utcnow()

    def ago(minutes: int) -> str:
        return iso(now - timedelta(minutes=minutes))

    def ahead(minutes: int) -> str:
        return iso(now + timedelta(minutes=minutes))

    orders = [
        # cust-1: badly late and still undelivered -> trips the escalation rule.
        ("ORD-1001", "cust-1", "Saffron House", "out_for_delivery", 42.50,
         ago(125), ago(95), None, "Ravi K."),
        # cust-1: delivered clean, useful as the boring happy path.
        ("ORD-1002", "cust-1", "Noodle Bar", "delivered", 18.00,
         ago(2880), ago(2835), ago(2840), "Priya S."),
        # cust-1: delivered but short two items -> missing-items path, $9.00 at stake.
        ("ORD-1003", "cust-1", "Green Bowl", "delivered", 31.25,
         ago(180), ago(140), ago(138), "Arun M."),
        # cust-2: just placed, on time, nothing wrong -> fast-model tracking answer.
        ("ORD-2001", "cust-2", "Pizza Forno", "preparing", 27.00,
         ago(10), ahead(25), None, None),
        # cust-3: cooked an hour ago, no courier ever collected it. 30 min past a 30-min
        # promise, so late and annoying but under ESCALATE_LATE_MINUTES. The money is
        # already spent on food nobody is carrying -- the case the remedy ladder exists
        # for. No courier assigned, which is what makes it `awaiting_courier`.
        ("ORD-3001", "cust-3", "Noodle Bar", "awaiting_courier", 30.00,
         ago(60), ago(30), None, None),
        # cust-4: same lateness, but a courier has it. Cancelling returns nothing.
        ("ORD-4001", "cust-4", "Noodle Bar", "out_for_delivery", 30.00,
         ago(60), ago(30), None, "Sunil T."),
        # cust-7: three refunds already in 30 days -> abuse pattern.
        ("ORD-7001", "cust-7", "Taco Loco", "delivered", 54.00,
         ago(20160), ago(20115), ago(20110), "Dev P."),
        ("ORD-7002", "cust-7", "Taco Loco", "delivered", 61.00,
         ago(14400), ago(14355), ago(14350), "Dev P."),
        ("ORD-7003", "cust-7", "Curry Point", "delivered", 48.00,
         ago(7200), ago(7155), ago(7150), "Meera J."),
        ("ORD-7004", "cust-7", "Curry Point", "delivered", 73.00,
         ago(60), ago(20), ago(18), "Meera J."),
    ]
    conn.executemany(
        "INSERT INTO orders (order_id, customer_id, restaurant, status, total_amount,"
        " placed_at, promised_at, delivered_at, courier)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        orders,
    )

    items = [
        ("ORD-1001", "Lamb Biryani", 1, 22.50),
        ("ORD-1001", "Garlic Naan", 2, 5.00),
        ("ORD-1001", "Mango Lassi", 2, 5.00),
        ("ORD-1002", "Pad Thai", 1, 14.00),
        ("ORD-1002", "Spring Rolls", 1, 4.00),
        ("ORD-1003", "Buddha Bowl", 1, 16.25),
        ("ORD-1003", "Miso Soup", 1, 6.00),
        ("ORD-1003", "Edamame", 1, 9.00),
        ("ORD-2001", "Margherita", 1, 19.00),
        ("ORD-2001", "Tiramisu", 1, 8.00),
        ("ORD-3001", "Chilli Garlic Noodles", 1, 24.00),
        ("ORD-3001", "Iced Jasmine Tea", 1, 6.00),
        ("ORD-4001", "Chilli Garlic Noodles", 1, 24.00),
        ("ORD-4001", "Iced Jasmine Tea", 1, 6.00),
        ("ORD-7004", "Chicken Korma", 2, 26.50),
        ("ORD-7004", "Pilau Rice", 2, 10.00),
    ]
    conn.executemany(
        "INSERT INTO order_items (order_id, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
        items,
    )

    refunds = [
        ("ORD-7001", "cust-7", 54.00, "Claimed order never arrived", iso(now - timedelta(days=14))),
        ("ORD-7002", "cust-7", 30.00, "Claimed food was cold", iso(now - timedelta(days=9))),
        ("ORD-7003", "cust-7", 48.00, "Claimed wrong order delivered", iso(now - timedelta(days=3))),
    ]
    conn.executemany(
        "INSERT INTO refunds (order_id, customer_id, amount, reason, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        refunds,
    )
