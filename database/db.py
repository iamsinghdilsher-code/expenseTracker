import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'expense_tracker.db')
PACIFIC = ZoneInfo("America/Los_Angeles")

DEFAULT_CATEGORIES = [
    "Bills", "Food", "Health", "Transport", "Entertainment", "Shopping", "Other"
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS umbrellas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS umbrella_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            umbrella_id INTEGER NOT NULL REFERENCES umbrellas(id),
            role TEXT NOT NULL DEFAULT 'member',
            created_at TEXT NOT NULL,
            UNIQUE(user_id, umbrella_id)
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES categories(id),
            umbrella_id INTEGER REFERENCES umbrellas(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            last_four TEXT NOT NULL,
            bank_name TEXT NOT NULL DEFAULT '',
            card_type TEXT NOT NULL DEFAULT '',
            user_id INTEGER NOT NULL REFERENCES users(id),
            umbrella_id INTEGER NOT NULL REFERENCES umbrellas(id),
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            date TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL
        );
    """)

    # Column migrations — each wrapped individually so one failure doesn't block the rest
    _alter_columns = [
        "ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'normal'",
        "ALTER TABLE expenses ADD COLUMN umbrella_id INTEGER REFERENCES umbrellas(id)",
        "ALTER TABLE expenses ADD COLUMN category_id INTEGER REFERENCES categories(id)",
        "ALTER TABLE expenses ADD COLUMN payment_method_id INTEGER REFERENCES payment_methods(id)",
        "ALTER TABLE expenses ADD COLUMN confidence_score REAL NOT NULL DEFAULT 1.0",
        "ALTER TABLE expenses ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'",
        "ALTER TABLE expenses ADD COLUMN dedup_hash TEXT",
    ]
    for sql in _alter_columns:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    # Partial unique index — NULLs (legacy rows) are excluded from the constraint
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_expenses_dedup"
        " ON expenses(dedup_hash) WHERE dedup_hash IS NOT NULL"
    )
    conn.commit()
    conn.close()


def _seed_categories(conn, umbrella_id, now_iso):
    """Insert default top-level categories for a new umbrella. No-op if already seeded."""
    if conn.execute(
        "SELECT id FROM categories WHERE umbrella_id = ?", (umbrella_id,)
    ).fetchone():
        return
    for name in DEFAULT_CATEGORIES:
        conn.execute(
            "INSERT INTO categories (name, umbrella_id, created_at) VALUES (?, ?, ?)",
            (name, umbrella_id, now_iso),
        )
    conn.commit()


def _create_home_umbrella(conn, user_id, now_iso):
    """Create a 'Home' umbrella for user_id, add them as admin, seed categories. Returns umbrella_id."""
    existing = conn.execute(
        "SELECT id FROM umbrellas WHERE owner_id = ? AND name = 'Home'", (user_id,)
    ).fetchone()
    if existing:
        return existing["id"]

    conn.execute(
        "INSERT INTO umbrellas (name, owner_id, created_at) VALUES ('Home', ?, ?)",
        (user_id, now_iso),
    )
    conn.commit()
    umbrella_id = conn.execute(
        "SELECT id FROM umbrellas WHERE owner_id = ? AND name = 'Home'", (user_id,)
    ).fetchone()["id"]

    conn.execute(
        "INSERT OR IGNORE INTO umbrella_access (user_id, umbrella_id, role, created_at)"
        " VALUES (?, ?, 'admin', ?)",
        (user_id, umbrella_id, now_iso),
    )
    conn.commit()
    _seed_categories(conn, umbrella_id, now_iso)
    return umbrella_id


def get_category_tree(conn, umbrella_id):
    """Returns top-level categories with nested children for an umbrella."""
    rows = conn.execute(
        "SELECT id, name, parent_id FROM categories WHERE umbrella_id = ? ORDER BY name",
        (umbrella_id,),
    ).fetchall()
    children_map = {}
    for r in rows:
        if r["parent_id"] is not None:
            children_map.setdefault(r["parent_id"], []).append(
                {"id": r["id"], "name": r["name"]}
            )
    return [
        {"id": r["id"], "name": r["name"], "children": children_map.get(r["id"], [])}
        for r in rows
        if r["parent_id"] is None
    ]


def seed_db(user_id):
    """Insert sample expenses for a newly registered user."""
    from datetime import timedelta
    today = datetime.now(PACIFIC).date()

    def _d(days_ago):
        return (today - timedelta(days=days_ago)).isoformat()

    samples = [
        # Bills
        (_d(74), "PG&E Electric Bill",     94.20,  "Bills"),
        (_d(44), "AT&T Phone Bill",         65.00,  "Bills"),
        (_d(14), "PG&E Electric Bill",      88.50,  "Bills"),
        # Food
        (_d(71), "Safeway Grocery",         87.43,  "Food"),
        (_d(61), "Starbucks Coffee",         6.75,  "Food"),
        (_d(34), "Trader Joe's",            54.10,  "Food"),
        (_d(14), "Safeway Grocery",         92.30,  "Food"),
        # Transport
        (_d(68), "Shell Gas Station",       55.00,  "Transport"),
        (_d(36), "Costco Gas #0673",        50.79,  "Transport"),
        (_d(4),  "Costco Gas #0673",        48.20,  "Transport"),
        # Shopping
        (_d(50), "Amazon Purchase",         34.99,  "Shopping"),
        (_d(32), "Target",                 120.45,  "Shopping"),
        # Entertainment
        (_d(79), "Netflix",                 15.99,  "Entertainment"),
        (_d(49), "Netflix",                 15.99,  "Entertainment"),
        (_d(19), "Netflix",                 15.99,  "Entertainment"),
        # Health
        (_d(69), "CVS Pharmacy",            22.50,  "Health"),
        (_d(10), "Doctor Visit Copay",      30.00,  "Health"),
    ]

    conn = get_db()
    now_iso = datetime.now(PACIFIC).isoformat()

    umbrella_id = _create_home_umbrella(conn, user_id, now_iso)

    cats = conn.execute(
        "SELECT id, name FROM categories WHERE umbrella_id = ?", (umbrella_id,)
    ).fetchall()
    cat_ids = {row["name"]: row["id"] for row in cats}
    other_id = cat_ids.get("Other")

    conn.executemany(
        "INSERT INTO expenses"
        " (user_id, umbrella_id, category_id, amount, category, description, date,"
        "  source, status, confidence_score, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'seed', 'confirmed', 1.0, ?)",
        [
            (user_id, umbrella_id, cat_ids.get(cat, other_id), amount, cat, desc, date, now_iso)
            for date, desc, amount, cat in samples
        ],
    )
    conn.commit()
    conn.close()
