"""Tests for registration, login, logout, and route-level access control."""
import pytest
from tests.conftest import register, login


class TestRegister:
    def test_get_returns_200(self, client):
        assert client.get("/register").status_code == 200

    def test_success_reaches_expenses(self, client):
        rv = register(client)
        assert rv.status_code == 200
        assert b"expense" in rv.data.lower()

    def test_duplicate_email_shows_error(self, client):
        register(client)
        client.get("/logout")  # must be logged out to hit the register form again
        rv = register(client)
        assert b"already exists" in rv.data.lower()

    def test_password_too_short(self, client):
        rv = client.post(
            "/register",
            data={"name": "Bob", "email": "bob@test.com", "password": "short1"},
            follow_redirects=True,
        )
        assert b"8 characters" in rv.data.lower()

    def test_missing_name(self, client):
        rv = client.post(
            "/register",
            data={"name": "", "email": "bob@test.com", "password": "password123"},
            follow_redirects=True,
        )
        assert b"required" in rv.data.lower()

    def test_missing_email(self, client):
        rv = client.post(
            "/register",
            data={"name": "Bob", "email": "", "password": "password123"},
            follow_redirects=True,
        )
        assert b"required" in rv.data.lower()

    def test_missing_password(self, client):
        rv = client.post(
            "/register",
            data={"name": "Bob", "email": "bob@test.com", "password": ""},
            follow_redirects=True,
        )
        assert b"required" in rv.data.lower()

    def test_already_logged_in_redirects_to_expenses(self, auth_client):
        rv = auth_client.get("/register", follow_redirects=False)
        assert rv.status_code == 302
        assert "/expenses" in rv.headers["Location"]

    def test_email_lowercased_on_register(self, client):
        rv = client.post(
            "/register",
            data={"name": "Bob", "email": "BOB@TEST.COM", "password": "password123"},
            follow_redirects=True,
        )
        assert rv.status_code == 200
        import database.db as dbmod
        conn = dbmod.get_db()
        row = conn.execute("SELECT email FROM users WHERE email = 'bob@test.com'").fetchone()
        conn.close()
        assert row is not None


class TestLogin:
    def test_get_returns_200(self, client):
        assert client.get("/login").status_code == 200

    def test_success_reaches_expenses(self, client):
        register(client)
        client.get("/logout")
        rv = login(client)
        assert rv.status_code == 200
        assert b"expense" in rv.data.lower()

    def test_wrong_password(self, client):
        register(client)
        client.get("/logout")  # must be logged out to reach the login form
        rv = client.post(
            "/login",
            data={"email": "alice@test.com", "password": "wrongpass"},
            follow_redirects=True,
        )
        assert b"incorrect" in rv.data.lower()

    def test_unknown_email(self, client):
        rv = client.post(
            "/login",
            data={"email": "nobody@test.com", "password": "password123"},
            follow_redirects=True,
        )
        assert b"incorrect" in rv.data.lower()

    def test_already_logged_in_redirects(self, auth_client):
        rv = auth_client.get("/login", follow_redirects=False)
        assert rv.status_code == 302
        assert "/expenses" in rv.headers["Location"]

    def test_email_case_insensitive(self, client):
        register(client)
        client.get("/logout")
        rv = client.post(
            "/login",
            data={"email": "ALICE@TEST.COM", "password": "password123"},
            follow_redirects=True,
        )
        assert b"expense" in rv.data.lower()


class TestLogout:
    def test_logout_redirects_to_landing(self, auth_client):
        rv = auth_client.get("/logout", follow_redirects=False)
        assert rv.status_code == 302

    def test_logout_clears_session(self, auth_client):
        auth_client.get("/logout")
        rv = auth_client.get("/expenses", follow_redirects=False)
        assert rv.status_code == 302
        assert "/login" in rv.headers["Location"]


class TestAccessControl:
    def test_expenses_unauthenticated(self, client):
        rv = client.get("/expenses", follow_redirects=False)
        assert rv.status_code == 302
        assert "/login" in rv.headers["Location"]

    def test_add_expense_unauthenticated(self, client):
        rv = client.get("/expenses/add", follow_redirects=False)
        assert rv.status_code == 302

    def test_admin_unauthenticated(self, client):
        rv = client.get("/admin", follow_redirects=False)
        assert rv.status_code == 302

    def test_admin_normal_user_redirected(self, auth_client):
        rv = auth_client.get("/admin", follow_redirects=False)
        assert rv.status_code == 302

    def test_profile_unauthenticated(self, client):
        rv = client.get("/profile", follow_redirects=False)
        assert rv.status_code == 302

    def test_payment_methods_unauthenticated(self, client):
        rv = client.get("/payment-methods", follow_redirects=False)
        assert rv.status_code == 302

    def test_switch_umbrella_unauthenticated(self, client):
        rv = client.get("/switch-umbrella/1", follow_redirects=False)
        assert rv.status_code == 302


class TestSwitchUmbrella:
    def test_switch_to_valid_umbrella(self, auth_client):
        import database.db as dbmod
        conn = dbmod.get_db()
        user = conn.execute("SELECT id FROM users WHERE email = 'alice@test.com'").fetchone()
        umbrella = conn.execute(
            "SELECT umbrella_id FROM umbrella_access WHERE user_id = ?", (user["id"],)
        ).fetchone()
        conn.close()
        rv = auth_client.get(
            f"/switch-umbrella/{umbrella['umbrella_id']}", follow_redirects=True
        )
        assert rv.status_code == 200

    def test_switch_to_unauthorized_umbrella_flashes_error(self, auth_client):
        rv = auth_client.get("/switch-umbrella/99999", follow_redirects=True)
        assert b"access" in rv.data.lower()
