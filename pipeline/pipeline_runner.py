"""
pipeline_runner.py

Core orchestration logic: Extract -> Bronze -> Silver validation -> Gold refresh.
Shared by both the daily incremental run (scheduler.py) and the historical
backfill script (backfill.py), so there's exactly one code path for "what
does it mean to process one day's data."
"""
from datetime import date, timedelta
from requests.exceptions import HTTPError
from pipeline.config import BASE_CURRENCY, TARGET_CURRENCIES
from pipeline.db import get_connection, init_db
from pipeline.extract import fetch_latest, fetch_for_date
from pipeline.load_bronze import insert_raw_rates, get_latest_bronze_date, seed_dim_currencies
from pipeline.transform_silver import validate_silver_for_date
from pipeline.transform_gold import ensure_dim_dates_covers
from pipeline.logger import get_logger

logger = get_logger(__name__)


def process_one_date(conn, target_date: date) -> dict:
    """
    Fetch and load a single date. Handles the "non-trading day" case
    gracefully: Frankfurter returns the nearest preceding trading day's
    data rather than erroring, so we detect that by comparing the
    requested date to api_response["date"] and log + skip the Bronze
    write if it's a date we already have (i.e. a weekend/holiday that
    just echoes back Friday's rate again).
    """
    date_str = target_date.isoformat()

    # Skip weekends before even calling the API
    if target_date.weekday() >= 5:
        logger.info(f"{date_str} is a weekend -- skipping.")
        return {"date": date_str, "status": "skipped_non_trading_day"}

    try:
        response = fetch_for_date(date_str)
    except HTTPError as e:
        logger.error(f"API error fetching {date_str}: {e}")
        return {"date": date_str, "status": "error", "error": str(e)}

    actual_date = response.get("date")
    if actual_date != date_str:
        logger.info(
            f"{date_str} is a public holiday -- "
            f"Frankfurter returned rates for {actual_date} instead. Skipping write."
        )
        return {"date": date_str, "status": "skipped_non_trading_day", "actual_date": actual_date}

    insert_raw_rates(conn, response)
    report = validate_silver_for_date(conn, actual_date, BASE_CURRENCY, TARGET_CURRENCIES)
    return {"date": date_str, "status": "loaded", "silver_report": report}


def run_daily() -> dict:
    """
    Incremental daily run: check the latest date in Bronze, fetch /latest,
    and only write if it's actually new data we don't already have.
    This is what the scheduler calls every morning.
    """
    init_db()
    conn = get_connection()
    try:
        seed_dim_currencies(conn)

        latest_bronze_date = get_latest_bronze_date(conn, BASE_CURRENCY)
        response = fetch_latest()
        api_date = response.get("date")

        if latest_bronze_date and api_date <= latest_bronze_date:
            logger.info(
                f"No new data: latest published rate is {api_date}, "
                f"already have {latest_bronze_date} in Bronze. Skipping."
            )
            return {"status": "no_new_data", "api_date": api_date, "bronze_date": latest_bronze_date}

        insert_raw_rates(conn, response)
        report = validate_silver_for_date(conn, api_date, BASE_CURRENCY, TARGET_CURRENCIES)
        ensure_dim_dates_covers(conn, date.today())

        logger.info(f"Daily run complete for {api_date}")
        return {"status": "loaded", "api_date": api_date, "silver_report": report}
    finally:
        conn.close()


def run_backfill(days: int) -> dict:
    """
    Loop over the last `days` calendar days using /[date], loading each
    trading day found. Non-trading days (weekends/holidays) are detected
    and skipped without failing the run -- see process_one_date().
    """
    init_db()
    conn = get_connection()
    results = {"loaded": 0, "skipped_non_trading_day": 0, "error": 0, "details": []}
    try:
        seed_dim_currencies(conn)
        today = date.today()
        ensure_dim_dates_covers(conn, today, lookback_days=days)

        start = today - timedelta(days=days)
        current = start
        while current <= today:
            result = process_one_date(conn, current)
            results["details"].append(result)
            results[result["status"]] = results.get(result["status"], 0) + 1
            current += timedelta(days=1)

        logger.info(
            f"Backfill complete: {results['loaded']} loaded, "
            f"{results['skipped_non_trading_day']} non-trading days skipped, "
            f"{results['error']} errors, over {days} days."
        )
        return results
    finally:
        conn.close()