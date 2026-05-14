import logging

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import DeviceToken, ForexPosition
from routers.forex_positions import _calculate_pnl, assistant_guidance
from services.forex_service import get_forex_mid_price
from services.forex_service import close_ig_position
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)

_NOTIFY_STATUSES = {"TAKE_PROFIT", "CUT_LOSS", "PROTECT_PROFIT", "HOLD_CAUTION"}


async def run_forex_position_monitoring() -> None:
    with Session(engine) as session:
        positions = session.exec(
            select(ForexPosition).where(ForexPosition.status == "open")
        ).all()

        if not positions:
            return

        logger.info("Forex position monitor: checking %d open practice positions.", len(positions))

        for pos in positions:
            try:
                _check_position(pos, session)
            except Exception as exc:
                logger.warning("Forex monitor error for %s %s: %s", pos.pair, pos.direction, exc)


def _check_position(pos: ForexPosition, session: Session) -> None:
    current_price = get_forex_mid_price(pos.pair)
    pnl, _ = _calculate_pnl(pos, current_price)
    status, message = assistant_guidance(pos, current_price, pnl)

    previous_status = pos.last_assistant_status
    pos.last_assistant_status = status
    session.add(pos)

    should_notify = (
        status in _NOTIFY_STATUSES
        and status != pos.last_notified_status
        and status != previous_status
    )

    if should_notify and settings.ENABLE_PUSH_NOTIFICATIONS:
        tokens = session.exec(
            select(DeviceToken).where(DeviceToken.user_id == pos.user_id)
        ).all()
        if tokens:
            title = _title_for_status(pos, status)
            body = _body_for_status(pos, status, message, current_price, pnl)
            sent = send_to_user_devices(
                [t.token for t in tokens],
                title=title,
                body=body,
                alert_id=pos.id,
                ticker=pos.pair,
                action_strength=100 if status in {"TAKE_PROFIT", "CUT_LOSS"} else 80,
            )
            if sent:
                pos.last_notified_status = status
                session.add(pos)
                logger.info("Forex monitor: push sent | pair=%s | status=%s", pos.pair, status)

    if _should_auto_close(pos, status):
        try:
            close_ig_position(pos.ig_deal_id, pos.direction, pos.ig_size)
            pos.status = "closed"
            pos.close_price = current_price
            pos.realised_pnl = pnl
            pos.last_notified_status = status
            logger.info("Forex monitor: IG demo auto-close sent | pair=%s | status=%s", pos.pair, status)
            if settings.ENABLE_PUSH_NOTIFICATIONS:
                tokens = session.exec(
                    select(DeviceToken).where(DeviceToken.user_id == pos.user_id)
                ).all()
                if tokens:
                    send_to_user_devices(
                        [t.token for t in tokens],
                        title=f"Forex auto-closed: {pos.pair}",
                        body=f"{pos.direction} {pos.pair} closed in IG demo. P/L £{pnl:.2f}" if pnl is not None else f"{pos.direction} {pos.pair} closed in IG demo.",
                        alert_id=pos.id,
                        ticker=pos.pair,
                        action_strength=100,
                    )
        except Exception as exc:
            logger.warning("Forex monitor: IG demo auto-close failed | pair=%s | status=%s | error=%s", pos.pair, status, exc)

    session.commit()


def _should_auto_close(pos: ForexPosition, status: str) -> bool:
    return (
        settings.ENABLE_FOREX_AUTO_CLOSE
        and settings.IG_ACCOUNT_TYPE.upper() == "DEMO"
        and status in {"TAKE_PROFIT", "CUT_LOSS"}
        and pos.ig_deal_id is not None
        and pos.ig_size is not None
        and pos.status == "open"
    )


def _title_for_status(pos: ForexPosition, status: str) -> str:
    labels = {
        "TAKE_PROFIT": "Forex target reached",
        "CUT_LOSS": "Forex stop reached",
        "PROTECT_PROFIT": "Forex profit review",
        "HOLD_CAUTION": "Forex caution",
    }
    return f"{labels.get(status, 'Forex update')}: {pos.pair}"


def _body_for_status(
    pos: ForexPosition,
    status: str,
    message: str,
    current_price: float | None,
    pnl: float | None,
) -> str:
    price_text = f" now {current_price:.5f}" if current_price is not None else ""
    pnl_text = f", P/L £{pnl:.2f}" if pnl is not None else ""
    action = {
        "TAKE_PROFIT": "Consider closing for profit.",
        "CUT_LOSS": "Close or review immediately.",
        "PROTECT_PROFIT": "Consider protecting the gain.",
        "HOLD_CAUTION": "Watch closely.",
    }.get(status, message)
    return f"{pos.direction} {pos.pair}{price_text}{pnl_text}. {action}"
