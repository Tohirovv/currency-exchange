-- ============================================================================
-- schema.sql
-- Bronze tables + dimension tables for the Currency Exchange pipeline.
-- Silver and Gold are implemented as VIEWS (see sql/views/) on top of these.
-- Target DB: SQLite
-- ============================================================================

-- ----------------------------------------------------------------------------
-- BRONZE LAYER
-- Raw, immutable copy of every API response. Never updated, only appended to.
-- One row per (fetch_date, base_currency) per pull. Re-fetching the same date
-- inserts a NEW row rather than overwriting -- the full history of pulls is
-- preserved as an audit log, and Silver always reads the latest one.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_rates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fetch_date      TEXT NOT NULL,          -- the rate date the API returned, YYYY-MM-DD
    base_currency   TEXT NOT NULL,
    raw_json        TEXT NOT NULL,          -- full API response, verbatim
    inserted_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_raw_rates_date_base
    ON raw_rates (fetch_date, base_currency);

-- ----------------------------------------------------------------------------
-- DIMENSION: dim_currencies
-- Static reference data. Loaded once (see pipeline/load_bronze.py:seed_dimensions)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_currencies (
    currency_code   TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    symbol          TEXT,
    country         TEXT
);

-- ----------------------------------------------------------------------------
-- DIMENSION: dim_dates
-- One row per calendar date. Generated for the full backfill + a buffer of
-- future dates so Gold joins never miss a date. See pipeline/transform_gold.py
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_dates (
    date            TEXT PRIMARY KEY,      -- YYYY-MM-DD
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    day             INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,      -- 0=Monday .. 6=Sunday
    is_weekday      INTEGER NOT NULL       -- 1=weekday, 0=weekend
);
