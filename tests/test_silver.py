"""
test_silver.py
Tests for the Silver view: invalid-rate filtering, deduplication on
re-fetch, and correct parsing of the raw JSON.
"""
from tests.conftest import insert_bronze_row


def test_valid_rates_pass_through(db):
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.93, "GBP": 0.79, "RUB": 90.5, "UZS": 12700.0})

    rows = db.execute("SELECT * FROM cleaned_rates ORDER BY target_currency").fetchall()
    currencies = {r[2] for r in rows}  # target_currency column

    assert currencies == {"EUR", "GBP", "RUB", "UZS"}
    assert len(rows) == 4


def test_negative_and_zero_rates_filtered_out(db):
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.93, "GBP": -1.0, "RUB": 0.0, "UZS": 12700.0})

    rows = db.execute("SELECT target_currency FROM cleaned_rates").fetchall()
    currencies = {r[0] for r in rows}

    assert "GBP" not in currencies, "Negative rate should be filtered out"
    assert "RUB" not in currencies, "Zero rate should be filtered out"
    assert currencies == {"EUR", "UZS"}


def test_null_rate_filtered_out(db):
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.93, "GBP": None})

    rows = db.execute("SELECT target_currency FROM cleaned_rates").fetchall()
    currencies = {r[0] for r in rows}

    assert currencies == {"EUR"}


def test_refetch_same_date_deduplicates_to_latest_insert(db):
    # First fetch: stale-looking rate
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.90})
    # Re-fetch same date later (e.g. ECB revised the rate): should win
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.93})

    rows = db.execute(
        "SELECT exchange_rate FROM cleaned_rates WHERE date = '2026-06-01' AND target_currency = 'EUR'"
    ).fetchall()

    assert len(rows) == 1, "Should not produce duplicate rows for the same date/currency"
    assert rows[0][0] == 0.93, "Should reflect the most recently inserted Bronze row"


def test_different_base_currencies_kept_separate(db):
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.93})
    insert_bronze_row(db, "2026-06-01", "EUR", {"USD": 1.07})

    rows = db.execute("SELECT base_currency, target_currency FROM cleaned_rates").fetchall()
    assert ("USD", "EUR") in rows
    assert ("EUR", "USD") in rows
    assert len(rows) == 2
