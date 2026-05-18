"""
APScheduler setup.
Runs in-process alongside FastAPI.
For production, move scanner_job to a separate Celery/RQ worker.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from workers.outcome_job import run_outcome_check
from workers.forex_position_monitor_job import run_forex_position_monitoring
from workers.forex_entry_scanner_job import run_forex_entry_scanner
from workers.cfd_entry_scanner_job import run_cfd_entry_scanner
from workers.forex_friday_close_job import run_forex_friday_close

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def _run_forex_position_monitoring() -> None:
    try:
        asyncio.run(run_forex_position_monitoring())
    except Exception as exc:
        logger.error("Forex position monitor failed: %s", exc)


def _run_forex_entry_scanner() -> None:
    try:
        asyncio.run(run_forex_entry_scanner())
    except Exception as exc:
        logger.error("Forex entry scanner failed: %s", exc)


def _run_cfd_entry_scanner() -> None:
    try:
        asyncio.run(run_cfd_entry_scanner())
    except Exception as exc:
        logger.error("CFD entry scanner failed: %s", exc)


def _run_forex_friday_close() -> None:
    try:
        asyncio.run(run_forex_friday_close())
    except Exception as exc:
        logger.error("Forex Friday close job failed: %s", exc)


def start_scheduler() -> None:
    scheduler.add_job(
        run_outcome_check,
        trigger=IntervalTrigger(hours=1),
        id="outcome_check",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_forex_position_monitoring,
        trigger=IntervalTrigger(minutes=5),
        id="forex_position_monitor",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_forex_entry_scanner,
        trigger=IntervalTrigger(minutes=settings.FOREX_ENTRY_SCAN_MINUTES),
        id="forex_entry_scanner",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_cfd_entry_scanner,
        trigger=IntervalTrigger(minutes=settings.CFD_ENTRY_SCAN_MINUTES),
        id="cfd_entry_scanner",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_forex_friday_close,
        trigger=IntervalTrigger(minutes=15),
        id="forex_friday_close",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        "Scheduler started (outcome_check=1h, forex_monitor=5m, forex_entry=%sm, "
        "cfd_entry=%sm, forex_friday_close=15m).",
        settings.FOREX_ENTRY_SCAN_MINUTES,
        settings.CFD_ENTRY_SCAN_MINUTES,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
