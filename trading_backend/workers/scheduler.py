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
from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import Strategy
from workers.outcome_job import run_outcome_check
from workers.scanner_job import run_strategy_scan
from workers.pie_monitor_job import run_pie_monitoring
from workers.holding_tracker_job import run_holding_tracker
from workers.forex_position_monitor_job import run_forex_position_monitoring
from workers.forex_entry_scanner_job import run_forex_entry_scanner
from workers.cfd_entry_scanner_job import run_cfd_entry_scanner

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def _run_all_strategies() -> None:
    """Synchronous wrapper that drives the async scanner for all enabled strategies."""
    with Session(engine) as session:
        strategies = session.exec(
            select(Strategy).where(Strategy.enabled == True)
        ).all()

    for strategy in strategies:
        try:
            asyncio.run(run_strategy_scan(strategy.id))
        except Exception as exc:
            logger.error("Strategy scan failed for %s: %s", strategy.id, exc)


def _run_pie_monitoring() -> None:
    try:
        asyncio.run(run_pie_monitoring())
    except Exception as exc:
        logger.error("Pie monitoring job failed: %s", exc)


def _run_holding_tracker() -> None:
    try:
        asyncio.run(run_holding_tracker())
    except Exception as exc:
        logger.error("Holding tracker job failed: %s", exc)


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


def start_scheduler() -> None:
    scheduler.add_job(
        _run_all_strategies,
        trigger=IntervalTrigger(minutes=15),
        id="market_scan",
        replace_existing=True,
        max_instances=1,
        # Run shortly after boot so we don't need to wait 15 minutes (and so frequent
        # service restarts during setup don't prevent the scanner from ever running).
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    scheduler.add_job(
        run_outcome_check,
        trigger=IntervalTrigger(hours=1),
        id="outcome_check",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_pie_monitoring,
        trigger=IntervalTrigger(hours=4),
        id="pie_monitor",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_holding_tracker,
        trigger=IntervalTrigger(minutes=30),
        id="holding_tracker",
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
    scheduler.start()
    logger.info(
        "Scheduler started (market_scan=15m, outcome_check=1h, pie_monitor=4h, "
        "holding_tracker=30m, forex_monitor=5m, forex_entry=%sm, cfd_entry=%sm).",
        settings.FOREX_ENTRY_SCAN_MINUTES,
        settings.CFD_ENTRY_SCAN_MINUTES,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
