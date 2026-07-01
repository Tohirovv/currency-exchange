"""
extract.py
Frankfurter API v2 client.

v2 key differences from v1:
  - target currencies param is called "quotes" not "symbols"
  - date is passed as a query param ?date=YYYY-MM-DD, not as a URL path segment
  - response is a list of objects, not a dict with a "rates" key

v2 response shape:
  [
    {"date": "2026-07-01", "base": "USD", "quote": "EUR", "rate": 0.89},
    {"date": "2026-07-01", "base": "USD", "quote": "UZS", "rate": 12021},
    ...
  ]

We normalize this into the shape the rest of the pipeline expects:
  {"amount": 1.0, "base": "USD", "date": "2026-07-01",
   "rates": {"EUR": 0.89, "UZS": 12021, ...}}
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


def _normalize(v2_response: list) -> dict:
    """
    Convert v2 list format into the shape the rest of the pipeline expects.
    """
    if not v2_response:
        raise ValueError("Empty response from API")

    date = v2_response[0].get("date")
    base = v2_response[0].get("base")
    rates = {row["quote"]: row["rate"] for row in v2_response}

    return {
        "amount": 1.0,
        "base": base,
        "date": date,
        "rates": rates,
    }


def fetch_latest(base: str = None, symbols: list[str] = None) -> dict:
    """Fetch the latest available trading day's rates."""
    base = base or BASE_CURRENCY
    symbols = symbols or TARGET_CURRENCIES
    url = f"{FRANKFURTER_BASE_URL}/rates"
    params = {"base": base, "quotes": ",".join(symbols)}

    logger.info(f"Fetching latest rates (base={base}, symbols={symbols})")
    response = _get(url, params)
    return _normalize(response.json())


def fetch_for_date(date: str, base: str = None, symbols: list[str] = None) -> dict:
    """
    Fetch rates for a specific date (YYYY-MM-DD).
    If date falls on a weekend/holiday, Frankfurter returns the nearest
    preceding trading day's rates with that date in the response.
    The caller should trust the returned date, not the requested date.
    """
    base = base or BASE_CURRENCY
    symbols = symbols or TARGET_CURRENCIES
    url = f"{FRANKFURTER_BASE_URL}/rates"
    params = {"base": base, "quotes": ",".join(symbols), "date": date}

    logger.info(f"Fetching rates for {date} (base={base}, symbols={symbols})")
    response = _get(url, params)
    return _normalize(response.json())


def fetch_currencies() -> dict:
    """Fetch the full currency list."""
    url = f"{FRANKFURTER_BASE_URL}/currencies"
    logger.info("Fetching currency reference list")
    response = _get(url, params={})
    return response.json()