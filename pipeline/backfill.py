"""
backfill.py
Standalone CLI for loading historical exchange rate data.

Usage:
    python -m pipeline.backfill                 # uses BACKFILL_DAYS from .env (default 730)
    python -m pipeline.backfill --days 365       # override: last 1 year
"""
import argparse
from pipeline.config import BACKFILL_DAYS
from pipeline.pipeline_runner import run_backfill
from pipeline.logger import get_logger

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Backfill historical currency exchange rates.")
    parser.add_argument(
        "--days", type=int, default=BACKFILL_DAYS,
        help=f"Number of days of history to backfill (default: {BACKFILL_DAYS}, from .env)",
    )
    args = parser.parse_args()

    logger.info(f"Starting backfill for the last {args.days} days...")
    results = run_backfill(args.days)

    print("\n--- Backfill Summary ---")
    print(f"  Loaded:               {results['loaded']}")
    print(f"  Non-trading days:     {results.get('skipped_non_trading_day', 0)}")
    print(f"  Errors:               {results.get('error', 0)}")
    print("------------------------\n")


if __name__ == "__main__":
    main()
