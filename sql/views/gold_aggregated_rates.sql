-- ============================================================================
-- gold_aggregated_rates.sql
--
-- Gold layer: aggregated_rates
--
-- Business-ready fact table built on top of Silver (cleaned_rates), enriched
-- with:
--   - rate_change_pct: day-over-day % change vs. the previous available
--     trading day for that currency pair (LAG over date-ordered rows)
--   - seven_day_avg: rolling average over the trailing 7 *trading-day* rows
--     (not calendar days -- weekends/holidays have no row, so this is
--     naturally a "last 7 published rates" average)
--   - joined to dim_currencies and dim_dates for descriptive attributes
--
-- Note: SQLite doesn't allow digits-leading identifiers (7_day_avg), so the
-- column is named seven_day_avg per the brief's "etc." flexibility.
-- ============================================================================

DROP VIEW IF EXISTS aggregated_rates;

CREATE VIEW aggregated_rates AS
WITH ordered AS (
    SELECT
        date,
        base_currency,
        target_currency,
        exchange_rate,
        load_timestamp,
        LAG(exchange_rate) OVER (
            PARTITION BY base_currency, target_currency
            ORDER BY date
        ) AS prev_rate,
        AVG(exchange_rate) OVER (
            PARTITION BY base_currency, target_currency
            ORDER BY date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS seven_day_avg
    FROM cleaned_rates
)
SELECT
    o.date,
    o.base_currency,
    o.target_currency,
    o.exchange_rate,
    ROUND(
        CASE
            WHEN o.prev_rate IS NULL OR o.prev_rate = 0 THEN NULL
            ELSE ((o.exchange_rate - o.prev_rate) / o.prev_rate) * 100.0
        END,
    4) AS rate_change_pct,
    ROUND(o.seven_day_avg, 6) AS seven_day_avg,
    c.name                    AS target_currency_name,
    c.symbol                  AS target_currency_symbol,
    c.country                 AS target_currency_country,
    d.year, d.month, d.day, d.is_weekday,
    o.load_timestamp
FROM ordered o
LEFT JOIN dim_currencies c ON c.currency_code = o.target_currency
LEFT JOIN dim_dates      d ON d.date = o.date;
