"""
Phase 1 migration: populate umbrellas, umbrella_access, categories for existing
users and backfill new expense columns (umbrella_id, category_id, status,
confidence_score).

Safe to run multiple times (idempotent).

Usage:
    python database/migrate.py
"""
import sqlite3
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'expense_tracker.db')
PACIFIC = ZoneInfo("America/Los_Angeles")

DEFAULT_CATEGORIES = [
    "Bills", "Food", "Health", "Transport", "Entertainment", "Shopping", "Other"
]


def run():
    if not os.path.exists(DB_PATH):
        print("Database not found — run the app first to create it.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    now_iso = datetime.now(PACIFIC).isoformat()

    users = conn.execute("SELECT id FROM users").fetchall()
    if not users:
        print("No users found — nothing to migrate.")
        conn.close()
        return

    for user in users:
        user_id = user["id"]

        # 1. Ensure a Home umbrella exists
        existing = conn.execute(
            "SELECT id FROM umbrellas WHERE owner_id = ? AND name = 'Home'", (user_id,)
        ).fetchone()
        if existing:
            umbrella_id = existing["id"]
        else:
            conn.execute(
                "INSERT INTO umbrellas (name, owner_id, created_at) VALUES ('Home', ?, ?)",
                (user_id, now_iso),
            )
            conn.commit()
            umbrella_id = conn.execute(
                "SELECT id FROM umbrellas WHERE owner_id = ? AND name = 'Home'", (user_id,)
            ).fetchone()["id"]

        # 2. Ensure umbrella_access record exists
        conn.execute(
            "INSERT OR IGNORE INTO umbrella_access (user_id, umbrella_id, role, created_at)"
            " VALUES (?, ?, 'admin', ?)",
            (user_id, umbrella_id, now_iso),
        )
        conn.commit()

        # 3. Seed default categories if not already present for this umbrella
        existing_cats = conn.execute(
            "SELECT id FROM categories WHERE umbrella_id = ?", (umbrella_id,)
        ).fetchall()
        if not existing_cats:
            for name in DEFAULT_CATEGORIES:
                conn.execute(
                    "INSERT INTO categories (name, umbrella_id, created_at) VALUES (?, ?, ?)",
                    (name, umbrella_id, now_iso),
                )
            conn.commit()

        cats = conn.execute(
            "SELECT id, name FROM categories WHERE umbrella_id = ?", (umbrella_id,)
        ).fetchall()
        cat_ids = {row["name"]: row["id"] for row in cats}
        other_id = cat_ids.get("Other")

        # 4. Backfill expenses missing umbrella_id or category_id
        expenses = conn.execute(
            "SELECT id, category FROM expenses"
            " WHERE user_id = ? AND (umbrella_id IS NULL OR category_id IS NULL)",
            (user_id,),
        ).fetchall()
        for exp in expenses:
            cat_id = cat_ids.get(exp["category"], other_id)
            conn.execute(
                "UPDATE expenses"
                " SET umbrella_id = ?, category_id = ?, status = 'confirmed', confidence_score = 1.0"
                " WHERE id = ?",
                (umbrella_id, cat_id, exp["id"]),
            )
        conn.commit()

        print(
            f"  User {user_id}: umbrella_id={umbrella_id},"
            f" categories={len(cat_ids)}, expenses backfilled={len(expenses)}"
        )

    print(f"\nPhase 1 migration complete — {len(users)} user(s) processed.")
    conn.close()


if __name__ == "__main__":
    run()
