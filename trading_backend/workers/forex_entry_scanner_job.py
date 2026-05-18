import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import DeviceToken, ForexEntryAlert, ForexPosition, User
from services.forex_service import DEFAULT_FOREX_PAIRS, get_forex_summary
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)


def _forex_market_open() -> bool:
    """Forex is closed from Friday 22:00 UTC to Sunday 22:00 UTC."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if weekday == 5:
        return False
    if weekday == 4 and now.hour >= 22:
        return False
    if weekday == 6 and now.hour < 22:
        return False
    return True


async def run_forex_entry_scanner() -> None:
    if not settings.ENABLE_FOREX_ENTRY_ALERTS:
        return
    if not _forex_market_open():
        logger.info("Forex entry scanner: market closed, skipping.")
        return

    with Session(engine) as session:
        users = session.exec(select(User).where(User.plan == "pro")).all()
        if not users and settings.is_private_test:
            users = [User(device_id=settings.TEST_USER_ID, plan="pro")]

        summary = get_forex_summary(timeframe="15m", pairs=DEFAULT_FOREX_PAIRS)
        actionable = [
            signal for signal in summary.signals
            if signal.direction in {"LONG", "SHORT"} and signal.strength >= settings.FOREX_MIN_SIGNAL_STRENGTH
        ]

        if not actionable:
            logger.info("Forex entry scanner: no actionable signals.")
            return

        logger.info(
            "Forex entry scanner: %d actionable signals | top=%s %s strength=%s provider=%s",
            len(actionable), actionable[0].pair, actionable[0].direction, actionable[0].strength, summary.provider,
        )

        for user in users:
            if user.id is None:
                session.add(user)
                session.commit()
                session.refresh(user)
            for signal in actionable:
                _maybe_alert_user(user, signal, session)


def _recent_entry_alert(user_id: str, pair: str, direction: str, session: Session) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FOREX_ENTRY_COOLDOWN_HOURS)
    existing = session.exec(
        select(ForexEntryAlert).where(
            ForexEntryAlert.user_id == user_id,
            ForexEntryAlert.pair == pair,
            ForexEntryAlert.direction == direction,
            # Treat declined alerts as part of cooldown to prevent repeated spam.
            ((ForexEntryAlert.push_sent == True) | (ForexEntryAlert.declined == True)),
            ForexEntryAlert.created_at >= cutoff,
        )
    ).first()
    return existing is not None


def _maybe_alert_user(user: User, signal, session: Session) -> None:
    if _user_has_open_position(user.id, signal.pair, signal.direction, session):
        logger.info(
            "Forex entry scanner: open position already exists | user=%s | pair=%s | direction=%s",
            user.id,
            signal.pair,
            signal.direction,
        )
        return

    if _recent_entry_alert(user.id, signal.pair, signal.direction, session):
        logger.info("Forex entry scanner: cooldown active | user=%s | pair=%s", user.id, signal.pair)
        return

    alert = ForexEntryAlert(
        user_id=user.id,
        pair=signal.pair,
        direction=signal.direction,
        strength=signal.strength,
        timeframe=signal.timeframe,
        entry_price=signal.entry,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        risk_amount=signal.risk_amount,
        position_units=signal.position_units,
        rationale=signal.rationale,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)

    if not settings.ENABLE_PUSH_NOTIFICATIONS:
        return

    tokens = session.exec(
        select(DeviceToken).where(DeviceToken.user_id == user.id)
    ).all()
    if not tokens:
        return

    title = f"{signal.pair} {signal.direction} — {signal.strength}/100"
    body = (
        f"Entry {signal.entry:.5f}, "
        f"stop {signal.stop_loss:.5f}, target {signal.take_profit:.5f}. "
        "Tap to review and place in IG."
    )
    sent = send_to_user_devices(
        [token.token for token in tokens],
        title=title,
        body=body,
        alert_id=alert.id,
        ticker=signal.pair,
        action_strength=signal.strength,
        notification_type="forex_entry_alert",
    )
    if sent:
        alert.push_sent = True
        session.add(alert)
        session.commit()
        logger.info("Forex entry scanner: push sent | user=%s | pair=%s | direction=%s", user.id, signal.pair, signal.direction)


def _user_has_open_position(user_id: str, pair: str, direction: str, session: Session) -> bool:
    existing = session.exec(
        select(ForexPosition).where(
            ForexPosition.user_id == user_id,
            ForexPosition.pair == pair,
            ForexPosition.direction == direction,
            ForexPosition.status == "open",
        )
    ).first()
    return existing is not None
