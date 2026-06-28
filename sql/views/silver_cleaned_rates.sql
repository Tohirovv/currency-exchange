-- ============================================================================
-- silver_cleaned_rates.sql
--
-- Silver layer: cleaned_rates
--
-- Reads the LATEST raw_rates row per (fetch_date, base_currency) -- this is
-- how we handle "never overwrite Bronze" while still always serving fresh
-- data: if the same date is fetched twice (e.g. a re-run, or today's rate
-- being revised by the ECB later in the day), Bronze gets a new row and
-- Silver simply picks the most recent insert via ROW_NUMBER().
--
-- Validation rules applied here (per the Silver layer contract):
--   - exchange_rate must be > 0
--   - exchange_rate must not be NULL / non-numeric
--   - duplicate (date, base_currency, target_currency) rows are collapsed
--     to the most recently inserted version
--
-- json_each() unpacks the `rates` object inside raw_json into rows of
-- (key, value) = (target_currency, exchange_rate).
-- ============================================================================

DROP VIEW IF EXISTS cleaned_rates;

CREATE VIEW cleaned_rates AS
WITH latest_per_date AS (
    -- Pick only the most recently inserted Bronze row for each
    -- (fetch_date, base_currency) pair, so re-fetches don't create dupes.
    SELECT
        id,
        fetch_date,
        base_currency,
        raw_json,
        inserted_at,
        ROW_NUMBER() OVER (
            PARTITION BY fetch_date, base_currency
            ORDER BY inserted_at DESC, id DESC
        ) AS rn
    FROM raw_rates
),
parsed AS (
    SELECT
        l.fetch_date                          AS date,
        l.base_currency                       AS base_currency,
        je.key                                AS target_currency,
        CAST(je.value AS REAL)                AS exchange_rate,
        l.inserted_at                         AS load_timestamp
    FROM latest_per_date l
    JOIN json_each(l.raw_json, '$.rates') je
    WHERE l.rn = 1
)
SELECT
    date,
    base_currency,
    target_currency,
    exchange_rate,
    load_timestamp
FROM parsed
WHERE exchange_rate IS NOT NULL
  AND exchange_rate > 0;
