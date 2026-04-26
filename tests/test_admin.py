"""Tests for the admin dashboard, draft management, budgets, and user permissions."""
import pytest
import database.db as dbmod
from tests.conftest import register, login


def _get_user(email="alice@test.com"):
    conn = dbmod.get_db()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    return row


def _get_umbrella_id(user_id):
    conn = dbmod.get_db()
    row = conn.execute(
        "SELECT umbrella_id FROM umbrella_access WHERE user_id=? LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    return row["umbrella_id"]


def _make_draft(umbrella_id, user_id):
    from app import _save_expense
    return _save_expense(
        user_id, 25.0, "Food", "Draft expense",
        "2024-07-01", "manual",
        umbrella_id=umbrella_id,
        confidence_score=0.5,
    )


class TestAdminAccess:
    def test_unauthenticated_redirected(self, client):
        rv = client.get("/admin", follow_redirects=False)
        assert rv.status_code == 302

    def test_normal_user_redirected(self, auth_client):
        rv = auth_client.get("/admin", follow_redirects=False)
        assert rv.status_code == 302

    def test_power_user_gets_200(self, power_client):
        assert power_client.get("/admin").status_code == 200

    def test_admin_month_param(self, power_client):
        assert power_client.get("/admin?month=2024-01").status_code == 200

    def test_admin_invalid_month_falls_back(self, power_client):
        assert power_client.get("/admin?month=garbage").status_code == 200

    def test_audit_trail_accessible(self, power_client):
        assert power_client.get("/admin/audit").status_code == 200

    def test_audit_filters(self, power_client):
        rv = power_client.get("/admin/audit?entity_type=expense&action=create")
        assert rv.status_code == 200


class TestDraftManagement:
    def test_confirm_draft_changes_status(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        eid = _make_draft(umb, user["id"])

        power_client.post(
            f"/admin/expenses/{eid}/confirm",
            data={"month": "2024-07"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        status = conn.execute("SELECT status FROM expenses WHERE id=?", (eid,)).fetchone()["status"]
        conn.close()
        assert status == "confirmed"

    def test_admin_delete_expense(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        eid = _make_draft(umb, user["id"])

        power_client.post(
            f"/admin/expenses/{eid}/delete",
            data={"month": "2024-07"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        assert conn.execute("SELECT id FROM expenses WHERE id=?", (eid,)).fetchone() is None
        conn.close()

    def test_normal_user_cannot_confirm(self, auth_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        eid = _make_draft(umb, user["id"])

        rv = auth_client.post(
            f"/admin/expenses/{eid}/confirm",
            data={"month": "2024-07"},
            follow_redirects=False,
        )
        assert rv.status_code == 302
        conn = dbmod.get_db()
        assert conn.execute("SELECT status FROM expenses WHERE id=?", (eid,)).fetchone()["status"] == "draft"
        conn.close()


class TestBudgetManagement:
    def test_budgets_page_accessible(self, power_client):
        assert power_client.get("/admin/budgets").status_code == 200

    def test_set_budget_creates_row(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        power_client.post(
            "/admin/budgets/set",
            data={"umbrella_id": str(umb), "category": "Food",
                  "amount": "500.00", "month": "2024-07"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        row = conn.execute(
            "SELECT amount FROM budgets WHERE umbrella_id=? AND category='Food' AND month='2024-07'",
            (umb,),
        ).fetchone()
        conn.close()
        assert row["amount"] == 500.0

    def test_set_budget_upserts_on_conflict(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        for amount in ["200.00", "350.00"]:
            power_client.post(
                "/admin/budgets/set",
                data={"umbrella_id": str(umb), "category": "Transport",
                      "amount": amount, "month": "2024-08"},
                follow_redirects=True,
            )
        conn = dbmod.get_db()
        rows = conn.execute(
            "SELECT amount FROM budgets WHERE umbrella_id=? AND category='Transport' AND month='2024-08'",
            (umb,),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["amount"] == 350.0

    def test_set_budget_missing_fields_flashes_error(self, power_client):
        rv = power_client.post(
            "/admin/budgets/set",
            data={"umbrella_id": "", "category": "", "amount": "", "month": "2024-07"},
            follow_redirects=True,
        )
        assert b"required" in rv.data.lower()

    def test_set_budget_zero_amount_rejected(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        rv = power_client.post(
            "/admin/budgets/set",
            data={"umbrella_id": str(umb), "category": "Food",
                  "amount": "0", "month": "2024-09"},
            follow_redirects=True,
        )
        assert b"positive" in rv.data.lower()

    def test_set_budget_negative_amount_rejected(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        rv = power_client.post(
            "/admin/budgets/set",
            data={"umbrella_id": str(umb), "category": "Food",
                  "amount": "-100", "month": "2024-09"},
            follow_redirects=True,
        )
        assert b"positive" in rv.data.lower()

    def test_delete_budget(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        power_client.post(
            "/admin/budgets/set",
            data={"umbrella_id": str(umb), "category": "Health",
                  "amount": "150.00", "month": "2024-07"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        bid = conn.execute(
            "SELECT id FROM budgets WHERE category='Health' AND month='2024-07'"
        ).fetchone()["id"]
        conn.close()

        power_client.post(f"/admin/budgets/{bid}/delete", follow_redirects=True)
        conn = dbmod.get_db()
        assert conn.execute("SELECT id FROM budgets WHERE id=?", (bid,)).fetchone() is None
        conn.close()

    def test_normal_user_cannot_set_budget(self, auth_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        rv = auth_client.post(
            "/admin/budgets/set",
            data={"umbrella_id": str(umb), "category": "Food",
                  "amount": "200", "month": "2024-07"},
            follow_redirects=False,
        )
        assert rv.status_code == 302


class TestUserManagement:
    def test_users_page_accessible(self, power_client):
        assert power_client.get("/admin/users").status_code == 200

    def test_toggle_normal_to_power(self, power_client):
        power_client.get("/logout")
        register(power_client, name="Bob", email="bob@test.com", password="password123")
        power_client.get("/logout")
        login(power_client, email="alice@test.com", password="password123")

        conn = dbmod.get_db()
        bob_id = conn.execute("SELECT id FROM users WHERE email='bob@test.com'").fetchone()["id"]
        conn.close()

        power_client.post(f"/admin/users/{bob_id}/role", follow_redirects=True)
        conn = dbmod.get_db()
        role = conn.execute("SELECT role FROM users WHERE id=?", (bob_id,)).fetchone()["role"]
        conn.close()
        assert role == "power"

    def test_toggle_power_to_normal(self, power_client):
        power_client.get("/logout")
        register(power_client, name="Bob", email="bob@test.com", password="password123")
        conn = dbmod.get_db()
        bob_id = conn.execute("SELECT id FROM users WHERE email='bob@test.com'").fetchone()["id"]
        conn.execute("UPDATE users SET role='power' WHERE id=?", (bob_id,))
        conn.commit()
        conn.close()

        power_client.get("/logout")
        login(power_client, email="alice@test.com", password="password123")

        power_client.post(f"/admin/users/{bob_id}/role", follow_redirects=True)
        conn = dbmod.get_db()
        role = conn.execute("SELECT role FROM users WHERE id=?", (bob_id,)).fetchone()["role"]
        conn.close()
        assert role == "normal"

    def test_cannot_toggle_own_role(self, power_client):
        alice_id = _get_user()["id"]
        rv = power_client.post(f"/admin/users/{alice_id}/role", follow_redirects=True)
        assert b"cannot change your own role" in rv.data.lower()

    def test_toggle_nonexistent_user(self, power_client):
        rv = power_client.post("/admin/users/99999/role", follow_redirects=True)
        assert b"not found" in rv.data.lower()


class TestUmbrellaGrants:
    def test_grant_umbrella_access(self, power_client):
        power_client.get("/logout")
        register(power_client, name="Bob", email="bob@test.com", password="password123")
        power_client.get("/logout")
        login(power_client, email="alice@test.com", password="password123")

        conn = dbmod.get_db()
        bob_id = conn.execute("SELECT id FROM users WHERE email='bob@test.com'").fetchone()["id"]
        alice = _get_user()
        umb = _get_umbrella_id(alice["id"])
        conn.close()

        power_client.post(
            f"/admin/users/{bob_id}/umbrella/grant",
            data={"umbrella_id": str(umb)},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        access = conn.execute(
            "SELECT id FROM umbrella_access WHERE user_id=? AND umbrella_id=?",
            (bob_id, umb),
        ).fetchone()
        conn.close()
        assert access is not None

    def test_revoke_umbrella_access(self, power_client):
        power_client.get("/logout")
        register(power_client, name="Bob", email="bob@test.com", password="password123")
        power_client.get("/logout")
        login(power_client, email="alice@test.com", password="password123")

        conn = dbmod.get_db()
        bob_id = conn.execute("SELECT id FROM users WHERE email='bob@test.com'").fetchone()["id"]
        alice = _get_user()
        umb = _get_umbrella_id(alice["id"])
        conn.close()

        # Grant first
        power_client.post(
            f"/admin/users/{bob_id}/umbrella/grant",
            data={"umbrella_id": str(umb)},
            follow_redirects=True,
        )
        # Then revoke
        power_client.post(
            f"/admin/users/{bob_id}/umbrella/{umb}/revoke",
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        access = conn.execute(
            "SELECT id FROM umbrella_access WHERE user_id=? AND umbrella_id=?",
            (bob_id, umb),
        ).fetchone()
        conn.close()
        assert access is None


class TestInviteLinks:
    def test_create_invite(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        rv = power_client.post(
            "/admin/invites/create",
            data={"umbrella_id": str(umb)},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        conn = dbmod.get_db()
        invite = conn.execute("SELECT id FROM invite_links WHERE umbrella_id=?", (umb,)).fetchone()
        conn.close()
        assert invite is not None

    def test_use_invite_link(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        power_client.post(
            "/admin/invites/create",
            data={"umbrella_id": str(umb)},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        invite = conn.execute("SELECT token FROM invite_links WHERE umbrella_id=?", (umb,)).fetchone()
        conn.close()

        # Log out Alice, register Bob, then use the invite as Bob
        power_client.get("/logout")
        register(power_client, name="Bob", email="bob@test.com", password="password123")
        rv = power_client.get(f"/invite/{invite['token']}", follow_redirects=True)
        assert rv.status_code == 200
        conn = dbmod.get_db()
        bob = conn.execute("SELECT id FROM users WHERE email='bob@test.com'").fetchone()
        access = conn.execute(
            "SELECT id FROM umbrella_access WHERE user_id=? AND umbrella_id=?",
            (bob["id"], umb),
        ).fetchone()
        conn.close()
        assert access is not None

    def test_expired_or_used_invite_shows_error(self, auth_client):
        rv = auth_client.get("/invite/invalid-token-xyz", follow_redirects=True)
        assert b"invalid" in rv.data.lower() or b"already been used" in rv.data.lower()

    def test_delete_invite(self, power_client):
        user = _get_user()
        umb = _get_umbrella_id(user["id"])
        power_client.post(
            "/admin/invites/create",
            data={"umbrella_id": str(umb)},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        invite = conn.execute("SELECT id FROM invite_links WHERE umbrella_id=?", (umb,)).fetchone()
        conn.close()

        power_client.post(f"/admin/invites/{invite['id']}/delete", follow_redirects=True)
        conn = dbmod.get_db()
        assert conn.execute("SELECT id FROM invite_links WHERE id=?", (invite["id"],)).fetchone() is None
        conn.close()
