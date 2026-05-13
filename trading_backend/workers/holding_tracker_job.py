"""
Holding tracker job.

Runs every 30 minutes during market hours.
For each open position owned by any user:
  1. Evaluates sell triggers via holding_reviewer.
  2. Updates peak_price in the DB.
  3. If a trigger fires and no REVIEW_SELL alert was sent in the last 4 hours:
     - Creates a REVIEW_SELL TradeAlert.
     - Sends a push notification.
     - Sets position.sell_alert_id.

No trades are placed. All actions are manual.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import (
    DeviceToken, OpenPosition, SignalPerformance, TradeAlert, AlertOutcome, User,
)
from models.schemas import ACTION_STRENGTH_DISCLAIMER
from services.holding_reviewer import evaluate_position
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)

_SELL_COOLDOWN_HOURS = 4


def _recent_sell_alert(user_id: str, ticker: str, session: Session) -> bool:
    """Return True if a REVIEW_SELL alert was already sent for this ticker recently."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_SELL_COOLDOWN_HOURS)
    existing = session.exec(
        select(TradeAlert).where(
            TradeAlert.user_id == user_id,
            TradeAlert.ticker == ticker,
            TradeAlert.action == "REVIEW_SELL",
            TradeAlert.created_at >= cutoff,
        )
    ).first()
    return existing is not None


async def run_holding_tracker() -> None:
    """Called by the scheduler every 30 min during market hours."""
    with Session(engine) as session:
        open_positions = session.exec(
            select(OpenPosition).where(OpenPosition.status == "open")
        ).all()

        if not open_positions:
            return

        logger.info("Holding tracker: checking %d open positions.", len(open_positions))

        for pos in open_positions:
            try:
                await _check_position(pos, session)
            except Exception as exc:
                logger.warning("Holding tracker error for %s: %s", pos.ticker, exc)


async def _check_position(pos: OpenPosition, session: Session) -> None:
    signal, new_peak = evaluate_position(
        ticker=pos.ticker,
        entry_price=pos.entry_price,
        amount=pos.amount,
        peak_price=pos.peak_price,
        opened_at=pos.opened_at,
    )

    # Always update peak price
    if new_peak and new_peak != pos.peak_price:
        pos.peak_price = new_peak
        session.add(pos)
        session.commit()

    if signal is None:
        logger.debug("Holding tracker: %s — no trigger.", pos.ticker)
        return

    # Check cooldown — don't spam sell alerts
    if _recent_sell_alert(pos.user_id, pos.ticker, session):
        logger.debug("Holding tracker: %s — trigger %s but cooldown active.", pos.ticker, signal.trigger)
        return

    logger.info(
        "Holding tracker: SELL TRIGGER | user=%s | ticker=%s | trigger=%s | gain=%.1f%%",
        pos.user_id, pos.ticker, signal.trigger, signal.gain_pct,
    )

    # Build REVIEW_SELL alert
    gain_pct = signal.gain_pct
    sell_alert = TradeAlert(
        id=str(uuid.uuid4()),
        user_id=pos.user_id,
        ticker=pos.ticker,
        action="REVIEW_SELL",
        signal_score=0,
        confidence=80,
        formula_score=0,
        claude_confidence=80,
        action_strength=80,
        action_label="Review Sell",
        score_interpretation=f"Sell trigger: {signal.trigger.replace('_', ' ')}",
        action_strength_disclaimer=ACTION_STRENGTH_DISCLAIMER,
        trading212_review_enabled=True,
        suggested_amount=pos.amount,
        price_at_alert=signal.current_price,
        alert_title=signal.title,
        alert_body=signal.body,
        what_is_this="",
        rationale=_rationale(signal.trigger, pos.ticker, gain_pct, signal.current_price, pos.entry_price),
        risk_note="You are responsible for the final decision. This app does not place trades.",
        key_factors=[_trigger_factor(signal.trigger, gain_pct)],
        blocking_risks=["Prices can reverse quickly — review the chart before selling."],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        executable=True,
        safety_flags=[],
        sell_trigger=signal.trigger,
    )
    session.add(sell_alert)
    session.add(AlertOutcome(alert_id=sell_alert.id))

    pos.sell_alert_id = sell_alert.id
    session.add(pos)
    session.commit()

    # Push notification
    if settings.ENABLE_PUSH_NOTIFICATIONS:
        tokens = session.exec(
            select(DeviceToken).where(DeviceToken.user_id == pos.user_id)
        ).all()
        if tokens:
            sent = send_to_user_devices(
                [t.token for t in tokens],
                title=signal.title,
                body=signal.body,
                alert_id=sell_alert.id,
                ticker=pos.ticker,
                action_strength=80,
            )
            if sent:
                sell_alert.push_sent = True
                session.add(sell_alert)
                session.commit()


def _rationale(trigger: str, ticker: str, gain_pct: float, current: float, entry: float) -> str:
    direction = "up" if gain_pct >= 0 else "down"
    abs_pct = abs(gain_pct)
    base = f"{ticker} is {direction} {abs_pct:.1f}% from your entry of £{entry:.2f} (now £{current:.2f}). "
    reasons = {
        "profit_target": f"It has reached the profit target of {settings.sell_target_pct:.0f}%. This is often a good point to take some profit.",
        "stop_loss": f"It has fallen past the stop-loss level of {settings.stop_loss_pct:.0f}%. Cutting losses early protects your remaining capital.",
        "overbought": "The price momentum indicator (RSI) is very high, which sometimes signals a short-term pullback ahead.",
        "stale": f"The price has barely moved in over {settings.stale_position_days} days. It may be worth reviewing whether to keep holding.",
    }
    return base + reasons.get(trigger, "Review this position manually.")


def _trigger_factor(trigger: str, gain_pct: float) -> str:
    return {
        "profit_target": f"Profit target reached ({gain_pct:.1f}% gain)",
        "stop_loss": f"Stop-loss level hit ({gain_pct:.1f}% loss)",
        "overbought": "Momentum indicator (RSI) is very high",
        "stale": "Position has barely moved in weeks",
    }.get(trigger, "Sell trigger fired")
