"""
test_bronze.py
Tests for Bronze write behavior: append-only, never overwrites, and
get_latest_bronze_date logic used for incremental fetching.
"""
from pipeline.load_bronze import insert_raw_rates, get_latest_bronze_date


def test_insert_raw_rates_appends_row(db):
    response = {"amount": 1.0, "base": "USD", "date": "2026-06-01", "rates": {"EUR": 0.93}}
    insert_raw_rates(db, response)

    count = db.execute("SELECT COUNT(*) FROM raw_rates").fetchone()[0]
    assert count == 1


def test_insert_raw_rates_never_overwrites_on_refetch(db):
    response_v1 = {"amount": 1.0, "base": "USD", "date": "2026-06-01", "rates": {"EUR": 0.90}}
    response_v2 = {"amount": 1.0, "base": "USD", "date": "2026-06-01", "rates": {"EUR": 0.93}}

    insert_raw_rates(db, response_v1)
    insert_raw_rates(db, response_v2)

    count = db.execute("SELECT COUNT(*) FROM raw_rates WHERE fetch_date = '2026-06-01'").fetchone()[0]
    assert count == 2, "Bronze must keep both rows -- it's an immutable append-only log"


def test_insert_raw_rates_rejects_malformed_response(db):
    import pytest
    malformed = {"amount": 1.0, "rates": {"EUR": 0.93}}  # missing "date" and "base"

    with pytest.raises(ValueError):
        insert_raw_rates(db, malformed)


def test_get_latest_bronze_date_returns_none_when_empty(db):
    assert get_latest_bronze_date(db, "USD") is None


def test_get_latest_bronze_date_returns_most_recent(db):
    insert_raw_rates(db, {"amount": 1.0, "base": "USD", "date": "2026-06-01", "rates": {"EUR": 0.90}})
    insert_raw_rates(db, {"amount": 1.0, "base": "USD", "date": "2026-06-03", "rates": {"EUR": 0.91}})
    insert_raw_rates(db, {"amount": 1.0, "base": "USD", "date": "2026-06-02", "rates": {"EUR": 0.92}})

    assert get_latest_bronze_date(db, "USD") == "2026-06-03"


def test_get_latest_bronze_date_is_scoped_to_base_currency(db):
    insert_raw_rates(db, {"amount": 1.0, "base": "USD", "date": "2026-06-01", "rates": {"EUR": 0.90}})
    insert_raw_rates(db, {"amount": 1.0, "base": "EUR", "date": "2026-06-05", "rates": {"USD": 1.07}})

    assert get_latest_bronze_date(db, "USD") == "2026-06-01"
    assert get_latest_bronze_date(db, "EUR") == "2026-06-05"
