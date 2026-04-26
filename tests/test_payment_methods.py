"""Tests for payment method CRUD and card-matching logic."""
import pytest
import database.db as dbmod


def _add_pm(client, last_four="1234", bank_name="Chase", card_type="Visa",
            follow_redirects=True):
    return client.post(
        "/payment-methods/add",
        data={"last_four": last_four, "bank_name": bank_name, "card_type": card_type},
        follow_redirects=follow_redirects,
    )


def _get_pm(last_four):
    conn = dbmod.get_db()
    row = conn.execute(
        "SELECT * FROM payment_methods WHERE last_four=?", (last_four,)
    ).fetchone()
    conn.close()
    return row


class TestPaymentMethodsList:
    def test_page_accessible(self, auth_client):
        assert auth_client.get("/payment-methods").status_code == 200

    def test_requires_login(self, client):
        rv = client.get("/payment-methods", follow_redirects=False)
        assert rv.status_code == 302


class TestAddPaymentMethod:
    def test_success(self, auth_client):
        _add_pm(auth_client)
        row = _get_pm("1234")
        assert row is not None
        assert row["bank_name"] == "Chase"
        assert row["card_type"] == "Visa"

    def test_letters_in_last_four(self, auth_client):
        rv = _add_pm(auth_client, last_four="abcd")
        assert b"4 numbers" in rv.data.lower()

    def test_too_short(self, auth_client):
        rv = _add_pm(auth_client, last_four="123")
        assert b"4 numbers" in rv.data.lower()

    def test_too_long(self, auth_client):
        rv = _add_pm(auth_client, last_four="12345")
        assert b"4 numbers" in rv.data.lower()

    def test_empty_last_four(self, auth_client):
        rv = _add_pm(auth_client, last_four="")
        assert b"4 numbers" in rv.data.lower()

    def test_duplicate_same_umbrella(self, auth_client):
        _add_pm(auth_client, last_four="5678")
        rv = _add_pm(auth_client, last_four="5678")
        assert b"already registered" in rv.data.lower()

    def test_blank_bank_name_allowed(self, auth_client):
        rv = _add_pm(auth_client, last_four="2222", bank_name="")
        # Should still succeed — bank_name is optional
        row = _get_pm("2222")
        assert row is not None

    def test_different_last_fours_both_saved(self, auth_client):
        _add_pm(auth_client, last_four="1111")
        _add_pm(auth_client, last_four="2222")
        conn = dbmod.get_db()
        count = conn.execute("SELECT COUNT(*) as c FROM payment_methods").fetchone()["c"]
        conn.close()
        assert count == 2


class TestEditPaymentMethod:
    def _create(self, auth_client, last_four="9012"):
        _add_pm(auth_client, last_four=last_four, bank_name="BofA")
        conn = dbmod.get_db()
        row = conn.execute("SELECT id FROM payment_methods WHERE last_four=?", (last_four,)).fetchone()
        conn.close()
        return row["id"]

    def test_get_edit_page(self, auth_client):
        pm_id = self._create(auth_client)
        assert auth_client.get(f"/payment-methods/{pm_id}/edit").status_code == 200

    def test_edit_success(self, auth_client):
        pm_id = self._create(auth_client)
        auth_client.post(
            f"/payment-methods/{pm_id}/edit",
            data={"last_four": "9012", "bank_name": "WellsFargo", "card_type": "Mastercard"},
            follow_redirects=True,
        )
        conn = dbmod.get_db()
        row = conn.execute("SELECT bank_name, card_type FROM payment_methods WHERE id=?", (pm_id,)).fetchone()
        conn.close()
        assert row["bank_name"] == "WellsFargo"
        assert row["card_type"] == "Mastercard"

    def test_edit_invalid_last_four(self, auth_client):
        pm_id = self._create(auth_client)
        rv = auth_client.post(
            f"/payment-methods/{pm_id}/edit",
            data={"last_four": "XX12", "bank_name": "BofA", "card_type": "Visa"},
            follow_redirects=True,
        )
        assert b"4 numbers" in rv.data.lower()

    def test_edit_not_found_redirects(self, auth_client):
        rv = auth_client.get("/payment-methods/99999/edit", follow_redirects=True)
        assert b"not found" in rv.data.lower()


class TestDeletePaymentMethod:
    def _create(self, auth_client, last_four="3456"):
        _add_pm(auth_client, last_four=last_four)
        conn = dbmod.get_db()
        row = conn.execute("SELECT id FROM payment_methods WHERE last_four=?", (last_four,)).fetchone()
        conn.close()
        return row["id"]

    def test_delete_success(self, auth_client):
        pm_id = self._create(auth_client)
        auth_client.post(f"/payment-methods/{pm_id}/delete", follow_redirects=True)
        conn = dbmod.get_db()
        assert conn.execute("SELECT id FROM payment_methods WHERE id=?", (pm_id,)).fetchone() is None
        conn.close()


class TestMatchPaymentMethod:
    def test_registered_card_matched(self, auth_client):
        _add_pm(auth_client, last_four="7777")
        conn = dbmod.get_db()
        user = conn.execute("SELECT id FROM users WHERE email='alice@test.com'").fetchone()
        umb = conn.execute(
            "SELECT umbrella_id FROM umbrella_access WHERE user_id=?", (user["id"],)
        ).fetchone()
        conn.close()

        from app import _match_payment_method
        assert _match_payment_method("7777", umb["umbrella_id"]) is not None

    def test_unregistered_card_returns_none(self, auth_client):
        from app import _match_payment_method
        conn = dbmod.get_db()
        user = conn.execute("SELECT id FROM users WHERE email='alice@test.com'").fetchone()
        umb = conn.execute(
            "SELECT umbrella_id FROM umbrella_access WHERE user_id=?", (user["id"],)
        ).fetchone()
        conn.close()
        assert _match_payment_method("9999", umb["umbrella_id"]) is None

    def test_none_last_four_returns_none(self, auth_client):
        from app import _match_payment_method
        assert _match_payment_method(None, 1) is None

    def test_none_umbrella_returns_none(self, auth_client):
        from app import _match_payment_method
        assert _match_payment_method("1234", None) is None

    def test_card_in_different_umbrella_not_matched(self, auth_client):
        """A card registered in umbrella A should not match queries for umbrella B."""
        _add_pm(auth_client, last_four="4444")
        from app import _match_payment_method
        # umbrella_id=99999 doesn't exist → should return None
        assert _match_payment_method("4444", 99999) is None
