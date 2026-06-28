"""
test_gold.py
Tests for the Gold view: day-over-day rate_change_pct, rolling
seven_day_avg, and dim_dates generation logic.
"""
from datetime import date
from tests.conftest import insert_bronze_row
from pipeline.load_bronze import seed_dim_dates, seed_dim_currencies


def test_day_over_day_change_pct(db):
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.90})
    insert_bronze_row(db, "2026-06-02", "USD", {"EUR": 0.99})  # +10%

    row = db.execute(
        "SELECT rate_change_pct FROM aggregated_rates WHERE date = '2026-06-02' AND target_currency = 'EUR'"
    ).fetchone()

    assert row is not None
    assert abs(row[0] - 10.0) < 0.01


def test_first_day_has_null_change_pct(db):
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.90})

    row = db.execute(
        "SELECT rate_change_pct FROM aggregated_rates WHERE date = '2026-06-01' AND target_currency = 'EUR'"
    ).fetchone()

    assert row[0] is None, "No prior day exists, so change_pct should be NULL, not 0 or an error"


def test_seven_day_rolling_average(db):
    # 7 days of EUR rates: 1.0 through 1.6, step 0.1
    rates = [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6]
    for i, rate in enumerate(rates, start=1):
        insert_bronze_row(db, f"2026-06-{i:02d}", "USD", {"EUR": rate})

    row = db.execute(
        "SELECT seven_day_avg FROM aggregated_rates WHERE date = '2026-06-07' AND target_currency = 'EUR'"
    ).fetchone()

    expected_avg = sum(rates) / 7
    assert abs(row[0] - expected_avg) < 0.001


def test_rolling_average_uses_only_available_days_at_start(db):
    # Only 3 days of data -- average should be over those 3, not divided by 7
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 1.0})
    insert_bronze_row(db, "2026-06-02", "USD", {"EUR": 2.0})
    insert_bronze_row(db, "2026-06-03", "USD", {"EUR": 3.0})

    row = db.execute(
        "SELECT seven_day_avg FROM aggregated_rates WHERE date = '2026-06-03' AND target_currency = 'EUR'"
    ).fetchone()

    assert abs(row[0] - 2.0) < 0.001  # avg(1,2,3) = 2.0, not avg over 7 slots


def test_gold_joins_dim_currencies_metadata(db):
    seed_dim_currencies(db)
    insert_bronze_row(db, "2026-06-01", "USD", {"EUR": 0.93})

    row = db.execute(
        "SELECT target_currency_name, target_currency_symbol, target_currency_country "
        "FROM aggregated_rates WHERE target_currency = 'EUR'"
    ).fetchone()

    assert row == ("Euro", "€", "Eurozone")


def test_dim_dates_generation_marks_weekends_correctly(db):
    # 2026-06-01 is a Monday, 2026-06-06 is a Saturday
    seed_dim_dates(db, date(2026, 6, 1), date(2026, 6, 7))

    monday = db.execute("SELECT is_weekday FROM dim_dates WHERE date = '2026-06-01'").fetchone()
    saturday = db.execute("SELECT is_weekday FROM dim_dates WHERE date = '2026-06-06'").fetchone()
    sunday = db.execute("SELECT is_weekday FROM dim_dates WHERE date = '2026-06-07'").fetchone()

    assert monday[0] == 1
    assert saturday[0] == 0
    assert sunday[0] == 0


def test_dim_dates_is_idempotent(db):
    seed_dim_dates(db, date(2026, 6, 1), date(2026, 6, 7))
    seed_dim_dates(db, date(2026, 6, 1), date(2026, 6, 7))  # run twice

    count = db.execute("SELECT COUNT(*) FROM dim_dates").fetchone()[0]
    assert count == 7, "Re-running seed_dim_dates should not create duplicate rows"
