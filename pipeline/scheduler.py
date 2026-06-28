"""
scheduler.py

Daily orchestration using the `schedule` library (chosen over APScheduler
for this project because: (1) the job is a single daily trigger with no
need for cron-like multi-job coordination or persistence across restarts,
and (2) its plain "every().day.at()" API is more readable for a small,
single-purpose pipeline -- APScheduler's extra features (job stores,
misfire grace periods, multiple triggers) aren't needed here).

Runs the daily pipeline at SCHEDULE_UTC_HOUR:SCHEDULE_UTC_MINUTE (default
03:00 UTC = 08:00 UTC+5 / Tashkent time), comfortably before the 8 AM
deadline since Frankfurter typically publishes by ~16:00 CET the prior day.

Run this as a long-lived process:
    python -m pipeline.scheduler
(in production, run under systemd/supervisor/cron @reboot, or a container
with a restart policy, so it survives reboots.)
"""
import time
import schedule
from pipeline.config import SCHEDULE_UTC_HOUR, SCHEDULE_UTC_MINUTE
from pipeline.pipeline_runner import run_daily
from pipeline.logger import get_logger

logger = get_logger(__name__)


def job():
    logger.info("Scheduled daily run triggered.")
    try:
        result = run_daily()
        logger.info(f"Daily run result: {result}")
    except Exception:
        # Catch-all so one bad run doesn't kill the long-lived scheduler process.
        logger.exception("Daily run failed with an unhandled exception.")


def main():
    run_time = f"{SCHEDULE_UTC_HOUR:02d}:{SCHEDULE_UTC_MINUTE:02d}"
    schedule.every().day.at(run_time).do(job)
    logger.info(f"Scheduler started. Daily run scheduled for {run_time} UTC.")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
