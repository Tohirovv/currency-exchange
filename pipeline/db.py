"""
db.py
Shared SQLite connection helper + schema/view initialization.
"""
import sqlite3
from pathlib import Path
from pipeline.config import DB_PATH, PROJECT_ROOT, resolve_path
from pipeline.logger import get_logger

logger = get_logger(__name__)

SQL_DIR = PROJECT_ROOT / "sql"


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite DB, creating the data dir if needed."""
    db_path = resolve_path(DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _run_sql_file(conn: sqlite3.Connection, path: Path) -> None:
    sql = path.read_text()
    conn.executescript(sql)


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """
    Create Bronze tables + dimension tables (schema.sql), then (re)create
    the Silver and Gold views on top of them. Safe to call repeatedly --
    tables use CREATE TABLE IF NOT EXISTS, views are dropped & recreated
    so view definitions always reflect the latest SQL on disk.
    """
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        logger.info("Initializing schema (tables)...")
        _run_sql_file(conn, SQL_DIR / "schema.sql")

        logger.info("Initializing Silver view (cleaned_rates)...")
        _run_sql_file(conn, SQL_DIR / "views" / "silver_cleaned_rates.sql")

        logger.info("Initializing Gold view (aggregated_rates)...")
        _run_sql_file(conn, SQL_DIR / "views" / "gold_aggregated_rates.sql")

        conn.commit()
        logger.info("Schema initialization complete.")
    finally:
        if owns_conn:
            conn.close()


if __name__ == "__main__":
    init_db()
