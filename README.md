# Currency Exchange Data Pipeline

A Medallion-architecture (Bronze → Silver → Gold) data pipeline that fetches
daily exchange rates from the [Frankfurter API](https://frankfurter.dev) for
**UZS, RUB, USD, EUR, and GBP** (USD as base), and serves them as
business-ready, enriched data in SQLite.

## Architecture

```
Frankfurter API
      │
      ▼
┌─────────────┐   raw JSON, append-only, never modified
│   BRONZE    │   table: raw_rates
└─────────────┘
      │
      ▼
┌─────────────┐   parsed, typed, validated (rate > 0), deduplicated
│   SILVER    │   SQL VIEW: cleaned_rates
└─────────────┘
      │
      ▼
┌─────────────┐   joined to dimensions, enriched with metrics
│    GOLD     │   SQL VIEW: aggregated_rates (+ dim_currencies, dim_dates)
└─────────────┘
```

### Why views for Silver and Gold, not tables

Exchange rates are immutable historical facts — once the ECB/Frankfurter
publishes the rate for `2026-01-15`, that number never changes again. That
removes the main reason populated tables usually win over views (avoiding
re-computation of a value that's still "live"). Since there's no staleness
risk, a view gives us:

- **Zero sync bugs.** There's no separate "did Silver get refreshed after
  the last Bronze load?" question — the view always reflects current Bronze
  data, by definition.
- **Less code.** No `transform_silver.py` / `transform_gold.py` write-path
  logic, no need to handle partial failures mid-write.
- **The window functions (`LAG`, rolling `AVG`) read naturally as SQL.**

The trade-off: every read of Gold re-computes the day-over-day diff and
7-day average from scratch. At this data volume (a handful of currencies,
a few years of daily data — a few thousand rows) that's negligible. At a
much larger scale, you'd materialize Gold as a table refreshed on a
schedule.

### Bronze immutability

`raw_rates` is **append-only**. Re-fetching a date you already have (e.g.
because today's not-yet-final rate gets revised, or the pipeline is
re-run) inserts a new row rather than overwriting the old one. The Silver
view picks the most recently inserted row per date via `ROW_NUMBER()`, so
the *output* is always fresh, while the *audit trail* of every API
response ever received is fully preserved in Bronze.

## Project Structure

```
currency-exchange/
├── README.md
├── .env.example
├── requirements.txt
├── pipeline/
│   ├── config.py            # loads .env, single source of truth for settings
│   ├── logger.py            # shared logging setup
│   ├── db.py                 # SQLite connection + schema/view init
│   ├── extract.py            # Frankfurter API client (with retries)
│   ├── load_bronze.py        # writes raw_rates, seeds dim_currencies/dim_dates
│   ├── transform_silver.py   # Silver validation + read helpers
│   ├── transform_gold.py     # Gold read helpers, dim_dates maintenance
│   ├── pipeline_runner.py    # shared orchestration: extract→bronze→validate
│   ├── backfill.py           # CLI: historical backfill
│   └── scheduler.py          # daily scheduled run
├── sql/
│   ├── schema.sql            # Bronze table + dimension tables
│   └── views/
│       ├── silver_cleaned_rates.sql
│       └── gold_aggregated_rates.sql
└── tests/
    ├── conftest.py            # in-memory DB fixture w/ real schema+views
    ├── test_bronze.py
    ├── test_silver.py
    └── test_gold.py
```

## Setup

```bash
git clone <your-repo-url>
cd currency-exchange
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # adjust if needed; defaults work out of the box
```

No database server to install — SQLite creates `data/currency_exchange.db`
automatically on first run.

## Running the pipeline

### 1. Initialize schema only (optional — happens automatically below too)

```bash
python -m pipeline.db
```

### 2. Historical backfill

```bash
python -m pipeline.backfill                 # uses BACKFILL_DAYS from .env (default: 730 days / ~2 years)
python -m pipeline.backfill --days 365       # override: last 1 year only
```

This loops over every calendar day in the window using the Frankfurter
`/[date]` endpoint. Weekends and holidays are detected automatically
(Frankfurter returns the prior trading day's data with that date in the
response — we compare it to the requested date and skip the write, logging
it as `skipped_non_trading_day` rather than an error).

### 3. Run once, right now (today's rate)

```bash
python -c "from pipeline.pipeline_runner import run_daily; print(run_daily())"
```

### 4. Run on a schedule (daily, automatically)

```bash
python -m pipeline.scheduler
```

This is a long-running process. It checks the latest date already in
Bronze before fetching, so if the day's rate isn't published yet or hasn't
changed, it logs `no_new_data` and exits cleanly rather than writing a
duplicate row. Scheduled for **03:00 UTC = 08:00 UTC+5 (Tashkent)** by
default — configurable via `SCHEDULE_UTC_HOUR` / `SCHEDULE_UTC_MINUTE` in
`.env`. In production, run this under `systemd`, `supervisor`, or a
container with a restart policy so it survives reboots.

**Why the `schedule` library over APScheduler:** this pipeline has exactly
one job with one daily trigger. `schedule`'s `every().day.at("03:00").do(job)`
is about as readable as it gets for that. APScheduler's extra machinery
(job stores, multiple trigger types, misfire grace windows) is built for
coordinating many jobs — overkill here, and would add a dependency and
config surface with no corresponding benefit at this scale.

## Querying the data

```bash
sqlite3 data/currency_exchange.db
```

```sql
-- Latest rate + day-over-day change + 7-day average, per currency
SELECT target_currency, exchange_rate, rate_change_pct, seven_day_avg
FROM aggregated_rates
WHERE date = (SELECT MAX(date) FROM aggregated_rates)
ORDER BY target_currency;
```

Or from Python:

```python
from pipeline.db import get_connection
from pipeline.transform_gold import summarize_latest

conn = get_connection()
print(summarize_latest(conn))
```

## Testing

```bash
python -m pytest tests/ -v
```

18 tests covering:
- **Bronze**: append-only behavior, never-overwrite on re-fetch, malformed
  response rejection, incremental-fetch date tracking.
- **Silver**: filtering of negative/zero/null rates, deduplication when a
  date is re-fetched, correct parsing per base currency.
- **Gold**: day-over-day `%` calculation (including the `NULL` edge case on
  day one), rolling 7-day average (including when fewer than 7 days of
  history exist), dimension joins, and `dim_dates` generation/idempotency.

Tests run against a real in-memory SQLite DB with the actual `schema.sql`
and view definitions applied — not mocks — so a bug in the SQL itself
would be caught, not just a bug in Python glue code.

## Known limitations / assumptions

- **USD is the default base currency**, matching the brief. Changing it
  (`BASE_CURRENCY` in `.env`) works without code changes, but historical
  Bronze data fetched under a different base is stored separately (see
  `test_get_latest_bronze_date_is_scoped_to_base_currency`) and won't be
  retroactively reconciled.
- **No intra-day updates.** Frankfurter publishes once daily (~16:00 CET);
  this pipeline mirrors that cadence and does not poll more frequently.
- **Today's rate can be revised.** Frankfurter notes that data for "today"
  isn't final and may update later in the day. Bronze handles this by
  accepting a new row on re-fetch rather than assuming the first value
  fetched is final.
- **`dim_dates` is generated, not fetched.** It covers the backfill window
  plus a 30-day forward buffer, regenerated (idempotently) whenever the
  pipeline runs, so Gold joins never hit a missing dimension row.
