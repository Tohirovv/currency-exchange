"""
conftest.py
Shared pytest fixtures: an isolated, in-memory SQLite DB with the real
schema + views applied, so tests exercise the actual SQL logic rather
than mocking it away.
"""
import json
import sqlite3
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = PROJECT_ROOT / "sql"


@pytest.fixture
def db():
    """Fresh in-memory SQLite DB with schema + Silver/Gold views applied."""
    conn = sqlite3.connect(":memory:")
    conn.executescript((SQL_DIR / "schema.sql").read_text())
    conn.executescript((SQL_DIR / "views" / "silver_cleaned_rates.sql").read_text())
    conn.executescript((SQL_DIR / "views" / "gold_aggregated_rates.sql").read_text())
    yield conn
    conn.close()


def insert_bronze_row(conn: sqlite3.Connection, fetch_date: str, base: str, rates: dict):
    """Helper: insert one raw_rates row shaped like a real Frankfurter response."""
    payload = {"amount": 1.0, "base": base, "date": fetch_date, "rates": rates}
    conn.execute(
        "INSERT INTO raw_rates (fetch_date, base_currency, raw_json) VALUES (?, ?, ?)",
        (fetch_date, base, json.dumps(payload)),
    )
    conn.commit()
