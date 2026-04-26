"""Unit tests for pure parsing/detection helper functions in app.py.

These tests require no database or Flask context — they exercise
_detect_category, _extract_last_four, _normalize_date, and the statement
parsers directly.
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from app import (
    _detect_category,
    _extract_last_four,
    _normalize_date,
    _parse_receipt_text,
    _parse_csv_statement,
    _parse_text_statement,
    _parse_email_sender,
    _strip_html,
)

PACIFIC = ZoneInfo("America/Los_Angeles")


class TestDetectCategory:
    def test_gas_station(self):
        assert _detect_category("Shell Gas Station") == "Transport"

    def test_costco_gas(self):
        assert _detect_category("Costco Gas #0673") == "Transport"

    def test_exxon(self):
        # "ExxonMobil" is one token — use a spaced description to hit word boundary
        assert _detect_category("Exxon Gas") == "Transport"

    def test_starbucks(self):
        assert _detect_category("Starbucks Coffee") == "Food"

    def test_safeway(self):
        assert _detect_category("Safeway Grocery") == "Food"

    def test_trader_joe(self):
        assert _detect_category("Trader Joe's") == "Food"

    def test_mcdonalds(self):
        assert _detect_category("McDonald's #4523") == "Food"

    def test_amazon(self):
        assert _detect_category("Amazon Purchase") == "Shopping"

    def test_walmart(self):
        assert _detect_category("Walmart Supercenter") == "Shopping"

    def test_netflix(self):
        assert _detect_category("Netflix Monthly") == "Entertainment"

    def test_spotify(self):
        assert _detect_category("Spotify Premium") == "Entertainment"

    def test_cvs_pharmacy(self):
        assert _detect_category("CVS Pharmacy") == "Health"

    def test_hospital(self):
        assert _detect_category("General Hospital copay") == "Health"

    def test_pge(self):
        assert _detect_category("PG&E Electric Bill") == "Bills"

    def test_att(self):
        assert _detect_category("AT&T Phone Bill") == "Bills"

    def test_comcast(self):
        assert _detect_category("Comcast Internet") == "Bills"

    def test_unknown_returns_other(self):
        assert _detect_category("Random Unknown Vendor 12345") == "Other"

    def test_case_insensitive(self):
        assert _detect_category("netflix") == "Entertainment"
        assert _detect_category("SAFEWAY") == "Food"

    def test_empty_string(self):
        assert _detect_category("") == "Other"


class TestExtractLastFour:
    def test_xxxx_uppercase(self):
        assert _extract_last_four("XXXX1234") == "1234"

    def test_ending_in_format(self):
        assert _extract_last_four("Card ending in 5678") == "5678"

    def test_ending_format_no_in(self):
        assert _extract_last_four("ending 9012") == "9012"

    def test_asterisk_format(self):
        assert _extract_last_four("****9012") == "9012"

    def test_xx_dash_format(self):
        assert _extract_last_four("xx-3456") == "3456"

    def test_no_match_returns_none(self):
        assert _extract_last_four("No card info here") is None

    def test_empty_returns_none(self):
        assert _extract_last_four("") is None

    def test_none_returns_none(self):
        assert _extract_last_four(None) is None

    def test_partial_digits_ignored(self):
        # 3 digits after xxxx should not match (needs exactly 4)
        assert _extract_last_four("XXXX123 extra") is None


class TestNormalizeDate:
    def test_iso_passthrough(self):
        assert _normalize_date("2024-03-15") == "2024-03-15"

    def test_mm_dd_yyyy_slash(self):
        assert _normalize_date("03/15/2024") == "2024-03-15"

    def test_mm_dd_yyyy_dash(self):
        assert _normalize_date("03-15-2024") == "2024-03-15"

    def test_two_digit_year(self):
        assert _normalize_date("03/15/24") == "2024-03-15"

    def test_single_digit_month_day(self):
        assert _normalize_date("1/5/2024") == "2024-01-05"

    def test_mm_dd_only_returns_valid_date(self):
        result = _normalize_date("01/01")
        assert len(result) == 10
        assert result.endswith("-01-01")

    def test_empty_returns_today(self):
        today = datetime.now(PACIFIC).strftime("%Y-%m-%d")
        assert _normalize_date("") == today

    def test_none_returns_today(self):
        today = datetime.now(PACIFIC).strftime("%Y-%m-%d")
        assert _normalize_date(None) == today

    def test_garbage_returns_today(self):
        today = datetime.now(PACIFIC).strftime("%Y-%m-%d")
        assert _normalize_date("not-a-date") == today

    def test_whitespace_stripped(self):
        assert _normalize_date("  2024-03-15  ") == "2024-03-15"


class TestParseReceiptText:
    def test_extracts_total_amount(self):
        result = _parse_receipt_text("Total: $42.50\nDate: 01/01/2024")
        assert result["amount"] == "42.50"

    def test_extracts_due_amount(self):
        result = _parse_receipt_text("Amount Due: 15.99")
        assert result["amount"] == "15.99"

    def test_fallback_dollar_sign(self):
        result = _parse_receipt_text("Charged $9.99 to your card")
        assert result["amount"] == "9.99"

    def test_extracts_date(self):
        result = _parse_receipt_text("Date: 03/15/2024\nTotal: $10.00")
        assert result["date"] == "03/15/2024"

    def test_merchant_from_explicit_field(self):
        result = _parse_receipt_text("Merchant: Whole Foods\nAmount: $55.00")
        assert result["description"] == "Whole Foods"

    def test_merchant_falls_back_to_first_line(self):
        result = _parse_receipt_text("Starbucks Coffee\nTotal: $6.75")
        assert "Starbucks" in result["description"]

    def test_category_inferred(self):
        result = _parse_receipt_text("Merchant: Netflix\nAmount: $15.99")
        assert result["category"] == "Entertainment"

    def test_last_four_extracted(self):
        result = _parse_receipt_text("Card XXXX1234\nTotal: $20.00")
        assert result["last_four"] == "1234"

    def test_no_last_four_returns_none(self):
        result = _parse_receipt_text("Total: $10.00")
        assert result["last_four"] is None

    def test_description_capped_at_80_chars(self):
        long_name = "A" * 100
        result = _parse_receipt_text(f"Merchant: {long_name}\nAmount: $5.00")
        assert len(result["description"]) <= 80


class TestParseCsvStatement:
    def test_basic_two_rows(self):
        csv = "Date,Description,Amount\n2024-01-15,Starbucks,6.75\n2024-01-16,Shell Gas,55.00"
        rows = _parse_csv_statement(csv)
        assert len(rows) == 2
        assert rows[0]["description"] == "Starbucks"
        assert rows[0]["amount"] == "6.75"
        assert rows[1]["category"] == "Transport"

    def test_zero_amount_skipped(self):
        csv = "Date,Description,Amount\n2024-01-15,Zero,0.00\n2024-01-16,Coffee,4.50"
        rows = _parse_csv_statement(csv)
        assert len(rows) == 1
        assert rows[0]["description"] == "Coffee"

    def test_malformed_amount_row_skipped(self):
        csv = "Date,Description,Amount\n2024-01-15,Bad,n/a\n2024-01-16,Good,5.00"
        rows = _parse_csv_statement(csv)
        assert len(rows) == 1
        assert rows[0]["description"] == "Good"

    def test_dollar_sign_stripped_from_amount(self):
        csv = "Date,Description,Amount\n2024-01-15,Coffee,$4.50"
        rows = _parse_csv_statement(csv)
        assert rows[0]["amount"] == "4.50"

    def test_comma_in_amount_handled(self):
        csv = "Date,Description,Amount\n2024-01-15,Big Purchase,\"1,500.00\""
        rows = _parse_csv_statement(csv)
        assert rows[0]["amount"] == "1500.00"

    def test_last_four_from_card_column(self):
        csv = "Date,Description,Amount,Card\n2024-01-15,Coffee,4.50,XXXX1234"
        rows = _parse_csv_statement(csv)
        assert rows[0]["last_four"] == "1234"

    def test_merchant_column_alias(self):
        csv = "Date,Merchant,Amount\n2024-01-15,Target,45.00"
        rows = _parse_csv_statement(csv)
        assert rows[0]["description"] == "Target"

    def test_empty_csv_returns_empty(self):
        assert _parse_csv_statement("") == []

    def test_capped_at_50_rows(self):
        lines = ["Date,Description,Amount"] + [
            f"2024-01-01,Item {i},{i + 1}.00" for i in range(60)
        ]
        rows = _parse_csv_statement("\n".join(lines))
        assert len(rows) == 50

    def test_date_normalized(self):
        csv = "Date,Description,Amount\n03/15/2024,Coffee,4.50"
        rows = _parse_csv_statement(csv)
        assert rows[0]["date"] == "2024-03-15"


class TestParseTextStatement:
    def test_basic_pattern(self):
        text = "01/15 Starbucks Coffee $6.75\n01/16/2024 Shell Gas $55.00"
        rows = _parse_text_statement(text)
        assert len(rows) == 2
        assert "Starbucks" in rows[0]["description"]

    def test_category_inferred(self):
        text = "01/15 Netflix $15.99"
        rows = _parse_text_statement(text)
        assert rows[0]["category"] == "Entertainment"

    def test_amount_without_dollar_sign(self):
        text = "01/15 Coffee 4.50"
        rows = _parse_text_statement(text)
        assert len(rows) == 1
        assert rows[0]["amount"] == "4.50"

    def test_empty_returns_empty(self):
        assert _parse_text_statement("") == []

    def test_no_pattern_returns_empty(self):
        assert _parse_text_statement("Just random text with no dates") == []

    def test_capped_at_50(self):
        lines = "\n".join(f"01/{i+1:02d} Item{i} ${i+1}.00" for i in range(55))
        rows = _parse_text_statement(lines)
        assert len(rows) == 50


class TestParseEmailSender:
    def test_name_plus_email_format(self):
        assert _parse_email_sender("Alice <alice@example.com>") == "alice@example.com"

    def test_plain_email(self):
        assert _parse_email_sender("alice@example.com") == "alice@example.com"

    def test_lowercases_result(self):
        assert _parse_email_sender("Alice <ALICE@EXAMPLE.COM>") == "alice@example.com"

    def test_none_returns_empty_string(self):
        assert _parse_email_sender(None) == ""

    def test_empty_string_returns_empty(self):
        assert _parse_email_sender("") == ""


class TestStripHtml:
    def test_removes_basic_tags(self):
        assert _strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_collapses_whitespace(self):
        result = _strip_html("<p>  Too   many   spaces  </p>")
        assert "  " not in result

    def test_none_returns_empty(self):
        assert _strip_html(None) == ""

    def test_plain_text_unchanged(self):
        assert _strip_html("No HTML here") == "No HTML here"

    def test_nested_tags(self):
        result = _strip_html("<div><span>Nested</span></div>")
        assert "Nested" in result
        assert "<" not in result
