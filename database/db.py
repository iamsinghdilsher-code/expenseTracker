import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'expense_tracker.db')
PACIFIC = ZoneInfo("America/Los_Angeles")


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
    # Migrate: add name column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()


def seed_db(user_id):
    """Insert sample expenses for a newly registered user so the dashboard isn't empty."""
    from datetime import date, timedelta
    today = datetime.now(PACIFIC).date()

    def _d(days_ago):
        return (today - timedelta(days=days_ago)).isoformat()

    samples = [
        # Bills
        (_d(74), "PG&E Electric Bill",       94.20,  "Bills"),
        (_d(44), "AT&T Phone Bill",           65.00,  "Bills"),
        (_d(14), "PG&E Electric Bill",        88.50,  "Bills"),
        # Food
        (_d(71), "Safeway Grocery",           87.43,  "Food"),
        (_d(61), "Starbucks Coffee",           6.75,  "Food"),
        (_d(34), "Trader Joe's",              54.10,  "Food"),
        (_d(14), "Safeway Grocery",           92.30,  "Food"),
        # Transport
        (_d(68), "Shell Gas Station",         55.00,  "Transport"),
        (_d(36), "Costco Gas #0673",          50.79,  "Transport"),
        (_d(4),  "Costco Gas #0673",          48.20,  "Transport"),
        # Shopping
        (_d(50), "Amazon Purchase",           34.99,  "Shopping"),
        (_d(32), "Target",                   120.45,  "Shopping"),
        # Entertainment
        (_d(79), "Netflix",                   15.99,  "Entertainment"),
        (_d(49), "Netflix",                   15.99,  "Entertainment"),
        (_d(19), "Netflix",                   15.99,  "Entertainment"),
        # Health
        (_d(69), "CVS Pharmacy",              22.50,  "Health"),
        (_d(10), "Doctor Visit Copay",        30.00,  "Health"),
    ]

    conn = get_db()
    now_iso = datetime.now(PACIFIC).isoformat()
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, description, date, source, created_at)"
        " VALUES (?, ?, ?, ?, ?, 'seed', ?)",
        [(user_id, amount, category, desc, date, now_iso) for date, desc, amount, category in samples],
    )
    conn.commit()
    conn.close()
