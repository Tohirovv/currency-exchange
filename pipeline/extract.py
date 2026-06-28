"""
extract.py
Thin client around the Frankfurter API. Supports both /latest and /[date]
endpoints. All requests are wrapped with retries (tenacity) since this is
a network call that can transiently fail.

Frankfurter API behavior worth knowing (informs Silver/scheduler logic):
  - /latest returns the most recent *trading day's* rates -- if today is a
    weekend/holiday, it returns the last published date, not today's date.
  - /{date} for a non-trading day (weekend/holiday) returns rates for the
    nearest PRECEDING trading day, with that earlier date in the response
    body -- it does not error or return empty.
  - Response shape: {"amount": 1.0, "base": "USD", "date": "2026-06-26",
    "rates": {"EUR": 0.93, "GBP": 0.79, ...}}
"""
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pipeline.config import FRANKFURTER_BASE_URL, BASE_CURRENCY, TARGET_CURRENCIES
from pipeline.logger import get_logger

logger = get_logger(__name__)

RETRYABLE_EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True,
)
def _get(url: str, params: dict) -> requests.Response:
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response


def fetch_latest(base: str = None, symbols: list[str] = None) -> dict:
    """Fetch the latest available trading day's rates."""
    base = base or BASE_CURRENCY
    symbols = symbols or TARGET_CURRENCIES
    url = f"{FRANKFURTER_BASE_URL}/latest"
    params = {"base": base, "symbols": ",".join(symbols)}

    logger.info(f"Fetching latest rates (base={base}, symbols={symbols})")
    response = _get(url, params)
    return response.json()


def fetch_for_date(date: str, base: str = None, symbols: list[str] = None) -> dict:
    """
    Fetch rates for a specific date (YYYY-MM-DD).
    Note: if `date` falls on a weekend/holiday, Frankfurter returns the
    nearest preceding trading day's rates, with that date reflected in the
    response's "date" field -- the caller should trust the response date,
    not assume it equals the requested date.
    """
    base = base or BASE_CURRENCY
    symbols = symbols or TARGET_CURRENCIES
    url = f"{FRANKFURTER_BASE_URL}/{date}"
    params = {"base": base, "symbols": ",".join(symbols)}

    logger.info(f"Fetching rates for {date} (base={base}, symbols={symbols})")
    response = _get(url, params)
    return response.json()


def fetch_currencies() -> dict:
    """Fetch the full {code: name} mapping of currencies Frankfurter tracks."""
    url = f"{FRANKFURTER_BASE_URL}/currencies"
    logger.info("Fetching currency reference list")
    response = _get(url, params={})
    return response.json()
