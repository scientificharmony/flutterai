"""
Phase 11 — Alert outcome tracker.
Runs periodically to record price at 1h, 4h, 1d, 5d after alert creation.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from database import engine
from models.db_models import TradeAlert, AlertOutcome, SignalPerformance
from services.market_data import get_current_price

logger = logging.getLogger(__name__)


def _pct_change(price_now: float, price_then: float) -> float:
    if price_then == 0:
        return 0.0
    return round((price_now - price_then) / price_then * 100, 4)


def run_outcome_check() -> None:
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        # Find all outcomes that still have gaps to fill
        outcomes = session.exec(
            select(AlertOutcome, TradeAlert)
            .join(TradeAlert, TradeAlert.id == AlertOutcome.alert_id)
            .where(AlertOutcome.price_5d.is_(None))
        ).all()

        for outcome, alert in outcomes:
            age = now - alert.created_at
            price_now = get_current_price(alert.ticker)
            if price_now is None:
                continue

            changed = False

            if outcome.price_1h is None and age >= timedelta(hours=1):
                outcome.price_1h = price_now
                changed = True

            if outcome.price_4h is None and age >= timedelta(hours=4):
                outcome.price_4h = price_now
                changed = True

            if outcome.price_1d is None and age >= timedelta(days=1):
                outcome.price_1d = price_now
                changed = True

            if outcome.price_5d is None and age >= timedelta(days=5):
                outcome.price_5d = price_now
                outcome.measured_at = now
                changed = True

            if changed:
                # Recompute max_gain / max_drawdown from available prices
                prices = [
                    p for p in [
                        outcome.price_1h, outcome.price_4h,
                        outcome.price_1d, outcome.price_5d,
                    ]
                    if p is not None
                ]
                if prices and alert.price_at_alert > 0:
                    pct_changes = [_pct_change(p, alert.price_at_alert) for p in prices]
                    outcome.max_gain = max(pct_changes)
                    outcome.max_drawdown = min(pct_changes)

                session.add(outcome)

                # Mirror into SignalPerformance
                perf = session.exec(
                    select(SignalPerformance).where(SignalPerformance.alert_id == alert.id)
                ).first()
                if perf:
                    perf.price_1h = outcome.price_1h
                    perf.price_4h = outcome.price_4h
                    perf.price_1d = outcome.price_1d
                    perf.price_5d = outcome.price_5d
                    perf.max_gain_1d = outcome.max_gain
                    perf.max_drawdown_1d = outcome.max_drawdown
                    perf.updated_at = now
                    session.add(perf)

        session.commit()
        logger.debug("Outcome check complete — processed %d outcomes.", len(outcomes))
