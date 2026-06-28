"""
load_bronze.py
Writes raw Frankfurter API responses into the Bronze table (raw_rates).
Bronze is treated as an immutable audit log: this module only INSERTs,
never UPDATEs or DELETEs existing rows.

Also responsible for seeding the static dim_currencies dimension table
(country/symbol metadata isn't in the Frankfurter response, so it's
hand-maintained here for the five currencies this project cares about,
with sensible fallbacks for any others).
"""
import json
import sqlite3
from datetime import date, timedelta
from pipeline.db import get_connection
from pipeline.logger import get_logger

logger = get_logger(__name__)

# Manually curated metadata for our five focus currencies (Frankfurter's
# /currencies endpoint only gives us {code: name}, no symbol/country).
CURRENCY_METADATA = {
    "USD": {"name": "US Dollar",         "symbol": "$",   "country": "United States"},
    "EUR": {"name": "Euro",              "symbol": "€",   "country": "Eurozone"},
    "GBP": {"name": "British Pound",     "symbol": "£",   "country": "United Kingdom"},
    "RUB": {"name": "Russian Ruble",     "symbol": "₽",   "country": "Russia"},
    "UZS": {"name": "Uzbekistani Som",   "symbol": "лв",  "country": "Uzbekistan"},
}


def insert_raw_rates(conn: sqlite3.Connection, api_response: dict) -> int:
    """
    Append one row to raw_rates for this API response.
    Returns the number of rows inserted (always 1 on success).

    Note: we always INSERT, never check-then-update. If the same date is
    fetched again (e.g. today's rate getting revised, or a manual re-run),
    a new row is added and the Silver view picks the most recently
    inserted one -- see sql/views/silver_cleaned_rates.sql.
    """
    fetch_date = api_response.get("date")
    base_currency = api_response.get("base")

    if not fetch_date or not base_currency:
        raise ValueError(f"Malformed API response, missing date/base: {api_response}")

    conn.execute(
        """
        INSERT INTO raw_rates (fetch_date, base_currency, raw_json)
        VALUES (?, ?, ?)
        """,
        (fetch_date, base_currency, json.dumps(api_response)),
    )
    conn.commit()
    logger.info(f"Bronze: inserted raw_rates row for {fetch_date} (base={base_currency})")
    return 1


def get_latest_bronze_date(conn: sqlite3.Connection, base_currency: str) -> str | None:
    """
    Return the most recent fetch_date already present in Bronze for this
    base currency, or None if Bronze is empty. Used by the scheduler for
    incremental logic -- only fetch dates after this one.
    """
    row = conn.execute(
        "SELECT MAX(fetch_date) FROM raw_rates WHERE base_currency = ?",
        (base_currency,),
    ).fetchone()
    return row[0] if row and row[0] else None


def seed_dim_currencies(conn: sqlite3.Connection) -> None:
    """Idempotently seed dim_currencies with our known metadata."""
    for code, meta in CURRENCY_METADATA.items():
        conn.execute(
            """
            INSERT INTO dim_currencies (currency_code, name, symbol, country)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(currency_code) DO UPDATE SET
                name = excluded.name,
                symbol = excluded.symbol,
                country = excluded.country
            """,
            (code, meta["name"], meta["symbol"], meta["country"]),
        )
    conn.commit()
    logger.info(f"Seeded dim_currencies with {len(CURRENCY_METADATA)} currencies")


def seed_dim_dates(conn: sqlite3.Connection, start: date, end: date) -> None:
    """
    Populate dim_dates for every calendar day in [start, end] inclusive.
    Re-runnable: uses INSERT OR IGNORE keyed on the date primary key.
    """
    rows = []
    current = start
    while current <= end:
        rows.append((
            current.isoformat(),
            current.year,
            current.month,
            current.day,
            current.weekday(),          # 0=Monday .. 6=Sunday
            1 if current.weekday() < 5 else 0,
        ))
        current += timedelta(days=1)

    conn.executemany(
        """
        INSERT OR IGNORE INTO dim_dates (date, year, month, day, day_of_week, is_weekday)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    logger.info(f"Seeded dim_dates: {len(rows)} dates from {start} to {end}")


if __name__ == "__main__":
    # Convenience: seed dimensions standalone, e.g. `python -m pipeline.load_bronze`
    conn = get_connection()
    try:
        seed_dim_currencies(conn)
        today = date.today()
        seed_dim_dates(conn, today - timedelta(days=730), today + timedelta(days=30))
    finally:
        conn.close()
