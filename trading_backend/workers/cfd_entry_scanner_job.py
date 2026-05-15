import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import CfdEntryAlert, DeviceToken, User
from services.cfd_service import DEFAULT_CFD_MARKETS, get_cfd_summary
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)


async def run_cfd_entry_scanner() -> None:
    if not settings.ENABLE_CFD_ENTRY_ALERTS:
        return

    with Session(engine) as session:
        users = session.exec(select(User).where(User.plan == "pro")).all()
        if not users and settings.is_private_test:
            users = [User(device_id=settings.TEST_USER_ID, plan="pro")]

        summary = get_cfd_summary(timeframe="15m", markets=DEFAULT_CFD_MARKETS)
        actionable = [
            s for s in summary.signals
            if s.direction in {"LONG", "SHORT"} and s.strength >= settings.CFD_MIN_SIGNAL_STRENGTH and s.epic
        ]

        if not actionable:
            logger.info("CFD entry scanner: no actionable signals.")
            return

        actionable.sort(key=lambda s: s.strength, reverse=True)
        top = actionable[0]
        logger.info(
            "CFD entry scanner: top=%s %s strength=%s provider=%s",
            top.market, top.direction, top.strength, summary.provider,
        )

        for user in users:
            if user.id is None:
                session.add(user)
                session.commit()
                session.refresh(user)
            _maybe_alert_user(user, top, session)


def _recent_entry_alert(user_id: str, market: str, direction: str, session: Session) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.CFD_ENTRY_COOLDOWN_HOURS)
    existing = session.exec(
        select(CfdEntryAlert).where(
            CfdEntryAlert.user_id == user_id,
            CfdEntryAlert.market == market,
            CfdEntryAlert.direction == direction,
            CfdEntryAlert.push_sent == True,
            CfdEntryAlert.created_at >= cutoff,
        )
    ).first()
    return existing is not None


def _maybe_alert_user(user: User, signal, session: Session) -> None:
    if _recent_entry_alert(user.id, signal.market, signal.direction, session):
        logger.info("CFD entry scanner: cooldown active | user=%s | market=%s", user.id, signal.market)
        return

    alert = CfdEntryAlert(
        user_id=user.id,
        market=signal.market,
        epic=signal.epic or "",
        direction=signal.direction,
        strength=signal.strength,
        timeframe=signal.timeframe,
        entry_price=signal.entry,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        risk_amount=signal.risk_amount,
        contract_size=signal.contract_size,
        rationale=signal.rationale,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)

    if not settings.ENABLE_PUSH_NOTIFICATIONS:
        return

    tokens = session.exec(select(DeviceToken).where(DeviceToken.user_id == user.id)).all()
    if not tokens:
        return

    title = f"CFD setup: {signal.market} {signal.direction}"
    body = (
        f"Strength {signal.strength}/100. Entry {signal.entry:.2f}, "
        f"stop {signal.stop_loss:.2f}, target {signal.take_profit:.2f}. "
        "Tap to review."
    )
    sent = send_to_user_devices(
        [t.token for t in tokens],
        title=title,
        body=body,
        alert_id=alert.id,
        ticker=signal.market,
        action_strength=signal.strength,
        notification_type="cfd_entry_alert",
    )
    if sent:
        alert.push_sent = True
        session.add(alert)
        session.commit()
        logger.info("CFD entry scanner: push sent | user=%s | market=%s | direction=%s", user.id, signal.market, signal.direction)

