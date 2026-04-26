import pytest
import database.db as dbmod
import app as app_module


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Flask app wired to a fresh per-test SQLite file."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(dbmod, "DB_PATH", db_file)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    app_module.app.config.update({"TESTING": True, "SECRET_KEY": "test-secret-key"})
    dbmod.init_db()
    yield app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------- helpers (importable by test modules) ----------

def register(client, name="Alice", email="alice@test.com", password="password123"):
    return client.post(
        "/register",
        data={"name": name, "email": email, "password": password},
        follow_redirects=True,
    )


def login(client, email="alice@test.com", password="password123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# ---------- convenience fixtures ----------

@pytest.fixture
def auth_client(client):
    """Client with a normal user (alice@test.com) already registered and logged in."""
    register(client)
    # Direct sign-up now creates a family head (power); reset to normal for test isolation.
    conn = dbmod.get_db()
    conn.execute("UPDATE users SET role = 'normal' WHERE email = 'alice@test.com'")
    conn.commit()
    conn.close()
    return client


@pytest.fixture
def power_client(client):
    """Client with alice@test.com registered and role elevated to 'power'."""
    register(client)
    conn = dbmod.get_db()
    conn.execute("UPDATE users SET role = 'power' WHERE email = 'alice@test.com'")
    conn.commit()
    conn.close()
    return client
