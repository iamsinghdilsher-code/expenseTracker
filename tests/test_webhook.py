"""Tests for the email inbound webhook (Phase 9)."""
import base64
import pytest
import database.db as dbmod

SECRET = "test-webhook-secret-abc"


def _post(client, token, payload):
    return client.post(
        f"/webhooks/email/inbound?token={token}",
        json=payload,
        content_type="application/json",
    )


def _payload(from_email="alice@test.com", text_body="", html_body="",
              attachments=None, subject="Test"):
    return {
        "From": f"Alice <{from_email}>",
        "Subject": subject,
        "TextBody": text_body,
        "HtmlBody": html_body,
        "Attachments": attachments or [],
    }


class TestWebhookAuth:
    def test_no_secret_env_returns_403(self, auth_client, monkeypatch):
        monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
        rv = _post(auth_client, "anything", _payload())
        assert rv.status_code == 403

    def test_wrong_token_returns_403(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        rv = _post(auth_client, "wrong-token", _payload())
        assert rv.status_code == 403

    def test_correct_token_allowed(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        rv = _post(auth_client, SECRET, _payload(text_body="nothing useful"))
        assert rv.status_code == 200


class TestWebhookSenderResolution:
    def test_unknown_sender_ignored(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        rv = _post(auth_client, SECRET, _payload(from_email="stranger@unknown.com"))
        data = rv.get_json()
        assert data["status"] == "ignored"
        assert data["reason"] == "sender not registered"

    def test_no_sender_ignored(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        payload = _payload()
        payload["From"] = ""
        rv = _post(auth_client, SECRET, payload)
        data = rv.get_json()
        assert data["status"] == "ignored"

    def test_sender_email_case_insensitive(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        rv = _post(auth_client, SECRET, _payload(
            from_email="ALICE@TEST.COM",
            text_body="01/15 Coffee $4.50\n01/16 Gas $55.00\n01/17 Netflix $15.99",
        ))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "ok"


class TestWebhookBodyParsing:
    def test_tabular_body_batch_parsed(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        body = (
            "01/15 Starbucks $6.75\n"
            "01/16 Shell Gas $55.00\n"
            "01/17 Netflix $15.99\n"
            "01/18 Amazon $34.99\n"
        )
        rv = _post(auth_client, SECRET, _payload(text_body=body))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["saved"] >= 3

        conn = dbmod.get_db()
        rows = conn.execute("SELECT * FROM expenses WHERE source='email'").fetchall()
        conn.close()
        assert len(rows) >= 3
        assert all(r["status"] == "draft" for r in rows)

    def test_single_receipt_body_parsed(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        body = "Merchant: Netflix\nTotal: $15.99\nDate: 2024-07-01"
        rv = _post(auth_client, SECRET, _payload(text_body=body, subject="Your charge"))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "ok"

    def test_html_body_fallback(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        html = (
            "<p>01/15 Coffee $4.50</p>"
            "<p>01/16 Gas $55.00</p>"
            "<p>01/17 Netflix $15.99</p>"
            "<p>01/18 Trader Joes $89.00</p>"
        )
        payload = _payload(html_body=html)
        payload["TextBody"] = ""
        rv = _post(auth_client, SECRET, payload)
        assert rv.status_code == 200

    def test_duplicate_emails_skipped(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        body = "01/15 Coffee $4.50\n01/16 Gas $55.00\n01/17 Netflix $15.99"
        p = _payload(text_body=body)
        _post(auth_client, SECRET, p)
        rv = _post(auth_client, SECRET, p)
        data = rv.get_json()
        assert data["skipped"] >= 3


class TestWebhookAttachments:
    def test_csv_attachment_parsed(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        csv = b"Date,Description,Amount\n2024-01-15,Starbucks,6.75\n2024-01-16,Shell,55.00"
        attachment = {
            "Name": "statement.csv",
            "ContentType": "text/csv",
            "Content": base64.b64encode(csv).decode(),
        }
        rv = _post(auth_client, SECRET, _payload(attachments=[attachment]))
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["saved"] >= 2

    def test_bad_attachment_content_gracefully_skipped(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        attachment = {
            "Name": "broken.csv",
            "ContentType": "text/csv",
            "Content": "!!! not valid base64 !!!",
        }
        rv = _post(auth_client, SECRET, _payload(attachments=[attachment]))
        assert rv.status_code == 200

    def test_empty_attachment_content_skipped(self, auth_client, monkeypatch):
        monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
        attachment = {"Name": "empty.csv", "ContentType": "text/csv", "Content": ""}
        rv = _post(auth_client, SECRET, _payload(attachments=[attachment]))
        assert rv.status_code == 200
