"""
config.py
Centralized configuration, loaded from environment variables (.env).
Nothing in this pipeline should hardcode currencies, dates, or paths --
everything funnels through this module.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root, if present. Falls back to real env vars
# (e.g. in CI or production) if no .env file exists.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _get_list(env_var: str, default: str) -> list[str]:
    raw = os.getenv(env_var, default)
    return [c.strip().upper() for c in raw.split(",") if c.strip()]


# --- Database ---
DB_PATH = os.getenv("DB_PATH", "./data/currency_exchange.db")

# --- API ---
FRANKFURTER_BASE_URL = os.getenv("FRANKFURTER_BASE_URL", "https://api.frankfurter.dev/v2")
BASE_CURRENCY = os.getenv("BASE_CURRENCY", "USD").upper()
TARGET_CURRENCIES = _get_list("TARGET_CURRENCIES", "UZS,RUB,EUR,GBP")

# --- Backfill ---
BACKFILL_DAYS = int(os.getenv("BACKFILL_DAYS", "730"))

# --- Scheduling ---
SCHEDULE_UTC_HOUR = int(os.getenv("SCHEDULE_UTC_HOUR", "3"))
SCHEDULE_UTC_MINUTE = int(os.getenv("SCHEDULE_UTC_MINUTE", "0"))

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "./logs/pipeline.log")


def resolve_path(relative_path: str) -> Path:
    """Resolve a config path relative to the project root, creating parent dirs."""
    path = (PROJECT_ROOT / relative_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
