"""
APScheduler setup.
Runs in-process alongside FastAPI.
For production, move scanner_job to a separate Celery/RQ worker.
"""
import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session, select

from database import engine
from models.db_models import Strategy
from workers.outcome_job import run_outcome_check
from workers.scanner_job import run_strategy_scan
from workers.pie_monitor_job import run_pie_monitoring

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


def start_scheduler() -> None:
    scheduler.add_job(
        _run_all_strategies,
        trigger=IntervalTrigger(minutes=15),
        id="market_scan",
        replace_existing=True,
        max_instances=1,
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
    scheduler.start()
    logger.info("Scheduler started (market_scan=15m, outcome_check=1h, pie_monitor=4h).")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
