import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import DeviceToken, ForexEntryAlert, User
from services.forex_service import DEFAULT_FOREX_PAIRS, get_forex_summary
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)


async def run_forex_entry_scanner() -> None:
    if not settings.ENABLE_FOREX_ENTRY_ALERTS:
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

        top = actionable[0]
        logger.info(
            "Forex entry scanner: top=%s %s strength=%s provider=%s",
            top.pair, top.direction, top.strength, summary.provider,
        )

        for user in users:
            if user.id is None:
                session.add(user)
                session.commit()
                session.refresh(user)
            _maybe_alert_user(user, top, session)


def _recent_entry_alert(user_id: str, pair: str, direction: str, session: Session) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.FOREX_ENTRY_COOLDOWN_HOURS)
    existing = session.exec(
        select(ForexEntryAlert).where(
            ForexEntryAlert.user_id == user_id,
            ForexEntryAlert.pair == pair,
            ForexEntryAlert.direction == direction,
            ForexEntryAlert.created_at >= cutoff,
        )
    ).first()
    return existing is not None


def _maybe_alert_user(user: User, signal, session: Session) -> None:
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

    title = f"Forex setup: {signal.pair} {signal.direction}"
    body = (
        f"Strength {signal.strength}/100. Entry {signal.entry:.5f}, "
        f"stop {signal.stop_loss:.5f}, target {signal.take_profit:.5f}. "
        "Enter manually in IG demo, then tap I took this practice trade."
    )
    sent = send_to_user_devices(
        [token.token for token in tokens],
        title=title,
        body=body,
        alert_id=alert.id,
        ticker=signal.pair,
        action_strength=signal.strength,
    )
    if sent:
        alert.push_sent = True
        session.add(alert)
        session.commit()
        logger.info("Forex entry scanner: push sent | user=%s | pair=%s | direction=%s", user.id, signal.pair, signal.direction)
