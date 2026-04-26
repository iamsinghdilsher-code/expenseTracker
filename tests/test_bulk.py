"""Tests for bulk import, CSV/text statement parsing endpoints, and draft status logic."""
import io
import pytest
import database.db as dbmod
from tests.conftest import register


def _bulk_post(client, expenses, content_type="application/json"):
    return client.post(
        "/expenses/add/bulk",
        json={"expenses": expenses},
        content_type=content_type,
    )


def _sample_expenses():
    return [
        {"amount": "25.00", "category": "Food", "description": "Bulk Lunch",
         "date": "2024-07-01"},
        {"amount": "55.00", "category": "Transport", "description": "Bulk Gas",
         "date": "2024-07-02"},
    ]


class TestBulkImport:
    def test_success_saves_all(self, auth_client):
        rv = _bulk_post(auth_client, _sample_expenses())
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["saved"] == 2
        assert data["skipped"] == 0

    def test_deduplication_skips_repeats(self, auth_client):
        expenses = _sample_expenses()
        _bulk_post(auth_client, expenses)
        rv = _bulk_post(auth_client, expenses)
        data = rv.get_json()
        assert data["saved"] == 0
        assert data["skipped"] == 2

    def test_partial_dedup(self, auth_client):
        expenses = _sample_expenses()
        _bulk_post(auth_client, expenses[:1])
        rv = _bulk_post(auth_client, expenses)
        data = rv.get_json()
        assert data["saved"] == 1
        assert data["skipped"] == 1

    def test_empty_list_returns_400(self, auth_client):
        rv = _bulk_post(auth_client, [])
        assert rv.status_code == 400
        assert "error" in rv.get_json()

    def test_non_json_body_returns_400(self, auth_client):
        rv = auth_client.post(
            "/expenses/add/bulk",
            data="not json at all",
            content_type="text/plain",
        )
        assert rv.status_code == 400

    def test_unregistered_card_sets_draft(self, auth_client):
        rv = _bulk_post(auth_client, [{
            "amount": "45.00", "category": "Shopping", "description": "Unknown card",
            "date": "2024-07-03", "last_four": "8888",
        }])
        assert rv.status_code == 200
        conn = dbmod.get_db()
        row = conn.execute("SELECT status FROM expenses WHERE description='Unknown card'").fetchone()
        conn.close()
        assert row["status"] == "draft"

    def test_registered_card_sets_confirmed(self, auth_client):
        auth_client.post(
            "/payment-methods/add",
            data={"last_four": "1111", "bank_name": "Chase", "card_type": "Visa"},
            follow_redirects=True,
        )
        rv = _bulk_post(auth_client, [{
            "amount": "30.00", "category": "Food", "description": "Known card",
            "date": "2024-07-04", "last_four": "1111",
        }])
        assert rv.status_code == 200
        conn = dbmod.get_db()
        row = conn.execute("SELECT status FROM expenses WHERE description='Known card'").fetchone()
        conn.close()
        assert row["status"] == "confirmed"

    def test_missing_date_uses_today(self, auth_client):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
        rv = _bulk_post(auth_client, [{
            "amount": "10.00", "category": "Food", "description": "No date item",
        }])
        assert rv.status_code == 200
        conn = dbmod.get_db()
        row = conn.execute("SELECT date FROM expenses WHERE description='No date item'").fetchone()
        conn.close()
        assert row["date"] == today

    def test_requires_login(self, client):
        rv = _bulk_post(client, _sample_expenses())
        assert rv.status_code == 302

    def test_source_set_to_statement(self, auth_client):
        _bulk_post(auth_client, [{
            "amount": "20.00", "category": "Food", "description": "Source check",
            "date": "2024-07-01",
        }])
        conn = dbmod.get_db()
        row = conn.execute("SELECT source FROM expenses WHERE description='Source check'").fetchone()
        conn.close()
        assert row["source"] == "statement"


class TestStatementEndpoint:
    def test_parse_pasted_text(self, auth_client):
        text = "01/15 Starbucks Coffee $6.75\n01/16 Shell Gas $55.00\n01/17 Netflix $15.99"
        rv = auth_client.post(
            "/expenses/add/statement",
            data={"paste_text": text},
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert "expenses" in data
        assert len(data["expenses"]) == 3

    def test_parse_csv_upload(self, auth_client):
        csv_bytes = b"Date,Description,Amount\n2024-01-15,Coffee,4.50\n2024-01-16,Gas,55.00"
        rv = auth_client.post(
            "/expenses/add/statement",
            data={"csv_file": (io.BytesIO(csv_bytes), "bank.csv")},
            content_type="multipart/form-data",
        )
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["expenses"]) == 2
        assert data["expenses"][0]["amount"] == "4.50"

    def test_no_input_returns_400(self, auth_client):
        rv = auth_client.post("/expenses/add/statement", data={})
        assert rv.status_code == 400

    def test_empty_paste_returns_400(self, auth_client):
        rv = auth_client.post("/expenses/add/statement", data={"paste_text": "   "})
        assert rv.status_code == 400

    def test_category_auto_detected_in_result(self, auth_client):
        text = "01/15 Netflix $15.99"
        rv = auth_client.post("/expenses/add/statement", data={"paste_text": text})
        data = rv.get_json()
        assert data["expenses"][0]["category"] == "Entertainment"

    def test_confidence_score_present(self, auth_client):
        text = "01/15 Coffee $4.50"
        rv = auth_client.post("/expenses/add/statement", data={"paste_text": text})
        data = rv.get_json()
        assert "confidence_score" in data["expenses"][0]
