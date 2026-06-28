"""
transform_silver.py

Silver is implemented as a SQL VIEW (sql/views/silver_cleaned_rates.sql) --
it parses, types, validates, and deduplicates Bronze data inline, on read.
There's no separate "load" step: the view IS the transformation.

This module's job is to:
  1. Provide a Python-side data quality check that runs after each Bronze
     load, comparing raw rows in vs. clean rows out, and logging/raising on
     anomalies the SQL view's WHERE clause silently filters out.
  2. Provide a convenience query function for other modules/tests to read
     Silver without writing raw SQL everywhere.

Why a view instead of a populated table: exchange rates are immutable
historical facts (today's USD/EUR rate from 2024-01-01 will never change),
so there is no "staleness" risk to a view here, and skipping a materialize
step removes an entire class of Bronze/Silver sync bugs.
"""
import sqlite3
from pipeline.db import get_connection
from pipeline.logger import get_logger

logger = get_logger(__name__)


def get_cleaned_rates(conn: sqlite3.Connection, date: str = None, target_currency: str = None) -> list[dict]:
    """Read from the Silver view, with optional filters. Used by tests and Gold."""
    query = "SELECT * FROM cleaned_rates WHERE 1=1"
    params = []
    if date:
        query += " AND date = ?"
        params.append(date)
    if target_currency:
        query += " AND target_currency = ?"
        params.append(target_currency.upper())

    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def validate_silver_for_date(conn: sqlite3.Connection, fetch_date: str, base_currency: str, expected_symbols: list[str]) -> dict:
    """
    Sanity-check that a Bronze load for `fetch_date` produced the expected
    rows in Silver. Logs warnings for any missing or filtered-out currency
    rather than failing the whole pipeline -- a single bad/missing rate
    shouldn't block the rest of the day's data.

    Returns a small report dict for the caller to log/inspect.
    """
    rows = get_cleaned_rates(conn, date=fetch_date)
    rows = [r for r in rows if r["base_currency"] == base_currency]
    found_currencies = {r["target_currency"] for r in rows}
    expected = {c.upper() for c in expected_symbols}

    missing = expected - found_currencies
    invalid_count = 0

    # Cross-check against raw Bronze to see if a "missing" currency was
    # present but filtered out (rate <= 0 / null) vs. just absent from the API.
    raw_row = conn.execute(
        "SELECT raw_json FROM raw_rates WHERE fetch_date = ? AND base_currency = ? "
        "ORDER BY inserted_at DESC LIMIT 1",
        (fetch_date, base_currency),
    ).fetchone()

    if raw_row:
        import json
        raw_rates = json.loads(raw_row[0]).get("rates", {})
        for code in missing:
            if code in raw_rates:
                invalid_count += 1
                logger.warning(
                    f"Silver validation: {code} present in Bronze for {fetch_date} "
                    f"but filtered out by Silver (rate={raw_rates[code]!r}, likely <= 0 or null)"
                )
            else:
                logger.warning(
                    f"Silver validation: {code} was not returned by the API for {fetch_date}"
                )

    report = {
        "fetch_date": fetch_date,
        "base_currency": base_currency,
        "rows_in_silver": len(rows),
        "expected_currencies": sorted(expected),
        "missing_currencies": sorted(missing),
        "invalid_filtered_count": invalid_count,
    }
    logger.info(f"Silver validation report: {report}")
    return report


if __name__ == "__main__":
    from pipeline.config import BASE_CURRENCY, TARGET_CURRENCIES
    from pipeline.load_bronze import get_latest_bronze_date

    conn = get_connection()
    try:
        latest = get_latest_bronze_date(conn, BASE_CURRENCY)
        if latest:
            validate_silver_for_date(conn, latest, BASE_CURRENCY, TARGET_CURRENCIES)
        else:
            logger.warning("No Bronze data found yet -- run the pipeline first.")
    finally:
        conn.close()
