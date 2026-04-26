"""Tests for the expense dashboard, CRUD operations, and core business logic."""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
import database.db as dbmod

PACIFIC = ZoneInfo("America/Los_Angeles")
TODAY = datetime.now(PACIFIC).strftime("%Y-%m-%d")


def _add(client, amount="25.00", category="Food", description="Test expense",
         date=TODAY, follow_redirects=True):
    return client.post(
        "/expenses/add",
        data={"amount": amount, "category": category, "description": description,
              "date": date, "source": "manual"},
        follow_redirects=follow_redirects,
    )


def _get_user(email="alice@test.com"):
    conn = dbmod.get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row


def _get_umbrella_id(user_id):
    conn = dbmod.get_db()
    row = conn.execute(
        "SELECT umbrella_id FROM umbrella_access WHERE user_id = ? LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    return row["umbrella_id"]


class TestExpensesDashboard:
    def test_requires_login(self, client):
        rv = client.get("/expenses", follow_redirects=False)
        assert rv.status_code == 302
        assert "/login" in rv.headers["Location"]

    def test_accessible_when_logged_in(self, auth_client):
        assert auth_client.get("/expenses").status_code == 200

    def test_month_filter(self, auth_client):
        assert auth_client.get("/expenses?month=2024-01").status_code == 200

    def test_invalid_month_falls_back_gracefully(self, auth_client):
        assert auth_client.get("/expenses?month=not-valid").status_code == 200

    def test_search_filter(self, auth_client):
        assert auth_client.get("/expenses?search=starbucks").status_code == 200

    def test_category_filter(self, auth_client):
        assert auth_client.get("/expenses?category=Food").status_code == 200


class TestAddExpense:
    def test_get_page(self, auth_client):
        assert auth_client.get("/expenses/add").status_code == 200

    def test_success_persists_to_db(self, auth_client):
        _add(auth_client, amount="45.00", description="Lunch meeting", date="2024-07-01")
        conn = dbmod.get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE description = 'Lunch meeting'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["amount"] == 45.0

    def test_invalid_amount_shows_error(self, auth_client):
        rv = _add(auth_client, amount="not-a-number")
        assert b"valid amount" in rv.data.lower()

    def test_zero_amount_allowed(self, auth_client):
        # zero passes float() and redirect happens — business decision, not a hard block
        rv = _add(auth_client, amount="0.00")
        assert rv.status_code == 200

    def test_duplicate_shows_warning(self, auth_client):
        _add(auth_client, amount="25.00", description="Dupe me", date="2024-06-01")
        rv = _add(auth_client, amount="25.00", description="Dupe me", date="2024-06-01")
        assert b"duplicate" in rv.data.lower()

    def test_empty_date_defaults_to_today(self, auth_client):
        auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Food", "description": "No date",
                  "date": "", "source": "manual"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        row = conn.execute("SELECT date FROM expenses WHERE description = 'No date'").fetchone()
        conn.close()
        assert row["date"] == TODAY

    def test_category_saved_correctly(self, auth_client):
        _add(auth_client, category="Transport", description="Gas fill", amount="50.00",
             date="2024-07-01")
        conn = dbmod.get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE description = 'Gas fill'"
        ).fetchone()
        conn.close()
        assert row["category"] == "Transport"


class TestConfidenceAndStatus:
    def _user_umbrella(self):
        user = _get_user()
        return user["id"], _get_umbrella_id(user["id"])

    def test_low_confidence_forced_to_draft(self, auth_client):
        from app import _save_expense
        uid, umb = self._user_umbrella()
        eid = _save_expense(uid, 20.0, "Food", "LowConf test", "2024-06-15", "manual",
                            umbrella_id=umb, confidence_score=0.60, status="confirmed")
        conn = dbmod.get_db()
        assert conn.execute("SELECT status FROM expenses WHERE id=?", (eid,)).fetchone()["status"] == "draft"
        conn.close()

    def test_boundary_confidence_085_stays_confirmed(self, auth_client):
        from app import _save_expense
        uid, umb = self._user_umbrella()
        eid = _save_expense(uid, 20.0, "Food", "Boundary conf", "2024-06-16", "manual",
                            umbrella_id=umb, confidence_score=0.85, status="confirmed")
        conn = dbmod.get_db()
        assert conn.execute("SELECT status FROM expenses WHERE id=?", (eid,)).fetchone()["status"] == "confirmed"
        conn.close()

    def test_high_confidence_stays_confirmed(self, auth_client):
        from app import _save_expense
        uid, umb = self._user_umbrella()
        eid = _save_expense(uid, 20.0, "Food", "HighConf test", "2024-06-17", "manual",
                            umbrella_id=umb, confidence_score=0.95, status="confirmed")
        conn = dbmod.get_db()
        assert conn.execute("SELECT status FROM expenses WHERE id=?", (eid,)).fetchone()["status"] == "confirmed"
        conn.close()

    def test_dedup_raises_on_exact_duplicate(self, auth_client):
        from app import _save_expense, DuplicateExpenseError
        uid, umb = self._user_umbrella()
        kwargs = dict(umbrella_id=umb)
        _save_expense(uid, 99.0, "Food", "Dedup sentinel", "2024-06-20", "manual", **kwargs)
        with pytest.raises(DuplicateExpenseError):
            _save_expense(uid, 99.0, "Food", "Dedup sentinel", "2024-06-20", "manual", **kwargs)

    def test_dedup_different_date_allowed(self, auth_client):
        from app import _save_expense
        uid, umb = self._user_umbrella()
        _save_expense(uid, 99.0, "Food", "Same but diff date", "2024-06-20", "manual", umbrella_id=umb)
        eid = _save_expense(uid, 99.0, "Food", "Same but diff date", "2024-06-21", "manual", umbrella_id=umb)
        assert eid is not None

    def test_dedup_different_user_allowed(self, auth_client):
        from app import _save_expense
        from tests.conftest import register
        uid, umb = self._user_umbrella()
        _save_expense(uid, 50.0, "Food", "MultiUser dedup", "2024-07-01", "manual", umbrella_id=umb)
        # Must log out Alice before registering Bob
        auth_client.get("/logout")
        register(auth_client, name="Bob", email="bob@test.com", password="password123")
        conn = dbmod.get_db()
        bob = conn.execute("SELECT id FROM users WHERE email='bob@test.com'").fetchone()
        bob_umb = conn.execute(
            "SELECT umbrella_id FROM umbrella_access WHERE user_id=?", (bob["id"],)
        ).fetchone()
        conn.close()
        eid = _save_expense(bob["id"], 50.0, "Food", "MultiUser dedup",
                            "2024-07-01", "manual", umbrella_id=bob_umb["umbrella_id"])
        assert eid is not None


class TestEditExpense:
    def _make(self, auth_client, description="Edit target"):
        _add(auth_client, amount="30.00", description=description, date="2024-07-01")
        conn = dbmod.get_db()
        row = conn.execute("SELECT id FROM expenses WHERE description=?", (description,)).fetchone()
        conn.close()
        return row["id"]

    def test_get_edit_page(self, auth_client):
        eid = self._make(auth_client)
        assert auth_client.get(f"/expenses/{eid}/edit").status_code == 200

    def test_edit_success(self, auth_client):
        eid = self._make(auth_client)
        auth_client.post(
            f"/expenses/{eid}/edit",
            data={"amount": "35.00", "category": "Transport", "description": "Updated",
                  "date": "2024-07-01"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        row = conn.execute("SELECT * FROM expenses WHERE id=?", (eid,)).fetchone()
        conn.close()
        assert row["amount"] == 35.0
        assert row["description"] == "Updated"
        assert row["category"] == "Transport"

    def test_edit_invalid_amount(self, auth_client):
        eid = self._make(auth_client)
        rv = auth_client.post(
            f"/expenses/{eid}/edit",
            data={"amount": "bad", "category": "Food", "description": "x", "date": "2024-07-01"},
            follow_redirects=True,
        )
        assert b"valid amount" in rv.data.lower()

    def test_edit_not_found(self, auth_client):
        rv = auth_client.get("/expenses/99999/edit", follow_redirects=True)
        assert b"not found" in rv.data.lower()

    def test_normal_user_cannot_edit_other_users_expense(self, client):
        from tests.conftest import register, login
        register(client, name="Alice", email="alice@test.com", password="password123")
        conn = dbmod.get_db()
        conn.execute("UPDATE users SET role='normal' WHERE email='alice@test.com'")
        conn.commit()
        conn.close()
        _add(client, description="Alice exclusive", date="2024-07-01")
        conn = dbmod.get_db()
        eid = conn.execute(
            "SELECT id FROM expenses WHERE description='Alice exclusive'"
        ).fetchone()["id"]
        conn.close()

        client.get("/logout")
        register(client, name="Bob", email="bob@test.com", password="password123")
        conn = dbmod.get_db()
        conn.execute("UPDATE users SET role='normal' WHERE email='bob@test.com'")
        conn.commit()
        conn.close()

        rv = client.get(f"/expenses/{eid}/edit", follow_redirects=True)
        assert b"not found" in rv.data.lower()


class TestDeleteExpense:
    def _make(self, auth_client, description="Delete target"):
        _add(auth_client, amount="15.00", description=description, date="2024-07-01")
        conn = dbmod.get_db()
        row = conn.execute("SELECT id FROM expenses WHERE description=?", (description,)).fetchone()
        conn.close()
        return row["id"]

    def test_delete_success(self, auth_client):
        eid = self._make(auth_client)
        auth_client.post(f"/expenses/{eid}/delete", follow_redirects=True)
        conn = dbmod.get_db()
        assert conn.execute("SELECT id FROM expenses WHERE id=?", (eid,)).fetchone() is None
        conn.close()

    def test_delete_other_users_expense_ignored(self, client):
        from tests.conftest import register, login
        register(client, name="Alice", email="alice@test.com", password="password123")
        conn = dbmod.get_db()
        conn.execute("UPDATE users SET role='normal' WHERE email='alice@test.com'")
        conn.commit()
        conn.close()
        _add(client, description="Alice only", date="2024-07-01")
        conn = dbmod.get_db()
        eid = conn.execute(
            "SELECT id FROM expenses WHERE description='Alice only'"
        ).fetchone()["id"]
        conn.close()

        client.get("/logout")
        register(client, name="Bob", email="bob@test.com", password="password123")
        conn = dbmod.get_db()
        conn.execute("UPDATE users SET role='normal' WHERE email='bob@test.com'")
        conn.commit()
        conn.close()

        client.post(f"/expenses/{eid}/delete", follow_redirects=True)
        conn = dbmod.get_db()
        # Expense still exists — Bob's DELETE WHERE user_id=Bob's id won't match
        assert conn.execute("SELECT id FROM expenses WHERE id=?", (eid,)).fetchone() is not None
        conn.close()

    def test_power_user_can_delete_any(self, power_client):
        from tests.conftest import register, login
        # Log out Alice, register Bob, add an expense as Bob, then log back in as Alice
        power_client.get("/logout")
        register(power_client, name="Bob", email="bob@test.com", password="password123")
        _add(power_client, description="Bob expense", date="2024-07-01")
        conn = dbmod.get_db()
        eid = conn.execute(
            "SELECT id FROM expenses WHERE description='Bob expense'"
        ).fetchone()["id"]
        conn.close()

        power_client.get("/logout")
        login(power_client, email="alice@test.com", password="password123")

        power_client.post(f"/expenses/{eid}/delete", follow_redirects=True)
        conn = dbmod.get_db()
        assert conn.execute("SELECT id FROM expenses WHERE id=?", (eid,)).fetchone() is None
        conn.close()


class TestExportCsv:
    def test_returns_csv_content_type(self, auth_client):
        rv = auth_client.get("/expenses/export")
        assert rv.status_code == 200
        assert "text/csv" in rv.content_type

    def test_response_has_header_row(self, auth_client):
        rv = auth_client.get("/expenses/export")
        assert b"Date,Description,Category,Amount" in rv.data

    def test_month_filter_applied(self, auth_client):
        rv = auth_client.get("/expenses/export?month=2024-01")
        assert rv.status_code == 200
        assert b"expenses_2024-01.csv" in rv.headers.get("Content-Disposition", "").encode()

    def test_invalid_month_ignored(self, auth_client):
        rv = auth_client.get("/expenses/export?month=bad-month")
        assert rv.status_code == 200
