"""
transform_gold.py

Gold is implemented as a SQL VIEW (sql/views/gold_aggregated_rates.sql),
joining the Silver view to dim_currencies and dim_dates and computing
rate_change_pct (day-over-day) and seven_day_avg (rolling) with window
functions. Like Silver, there's no separate "load" step -- the view is
always fresh because it's built on Silver, which is built on Bronze.

This module's job:
  1. Keep dim_dates extended far enough forward/backward that Gold joins
     never produce a NULL dimension row for a valid trading day.
  2. Provide convenience read functions for the demo / notebooks / tests.
"""
import sqlite3
from datetime import date, timedelta
from pipeline.db import get_connection
from pipeline.load_bronze import seed_dim_dates
from pipeline.logger import get_logger

logger = get_logger(__name__)


def ensure_dim_dates_covers(conn: sqlite3.Connection, through_date: date, lookback_days: int = 730) -> None:
    """
    Make sure dim_dates has rows from (through_date - lookback_days) up to
    (through_date + 30). Called before reading Gold so a fresh backfill or
    a new day's fetch always has a matching dim_dates row to join against.
    """
    start = through_date - timedelta(days=lookback_days)
    end = through_date + timedelta(days=30)
    seed_dim_dates(conn, start, end)


def get_aggregated_rates(
    conn: sqlite3.Connection,
    target_currency: str = None,
    start_date: str = None,
    end_date: str = None,
) -> list[dict]:
    """Read from the Gold view with optional filters. Used by tests/demo/notebooks."""
    query = "SELECT * FROM aggregated_rates WHERE 1=1"
    params = []
    if target_currency:
        query += " AND target_currency = ?"
        params.append(target_currency.upper())
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date"

    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def summarize_latest(conn: sqlite3.Connection) -> list[dict]:
    """Convenience: latest available row per target currency, for quick demo output."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT *
        FROM aggregated_rates
        WHERE date = (SELECT MAX(date) FROM aggregated_rates)
        ORDER BY target_currency
        """
    ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    conn = get_connection()
    try:
        ensure_dim_dates_covers(conn, date.today())
        summary = summarize_latest(conn)
        for row in summary:
            logger.info(
                f"{row['target_currency']}: rate={row['exchange_rate']}, "
                f"change={row['rate_change_pct']}%, 7d_avg={row['seven_day_avg']}"
            )
    finally:
        conn.close()
