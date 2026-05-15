import logging
from datetime import datetime, timezone

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import DeviceToken, ForexPosition
from routers.forex_positions import _calculate_pnl
from services.forex_service import close_ig_position, get_forex_mid_price, provider_connected
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)


def _is_friday_close_window() -> bool:
    """True between Friday 21:00 and 22:00 UTC — one hour before forex weekend close."""
    now = datetime.now(timezone.utc)
    return now.weekday() == 4 and 21 <= now.hour < 22


async def run_forex_friday_close() -> None:
    """Close any open positions that are in profit before the weekend market close."""
    if not _is_friday_close_window():
        return
    if not settings.ENABLE_FOREX_AUTO_CLOSE:
        return
    if not provider_connected():
        logger.info("Forex Friday close: IG not connected, skipping.")
        return

    with Session(engine) as session:
        positions = session.exec(
            select(ForexPosition).where(ForexPosition.status == "open")
        ).all()

        if not positions:
            logger.info("Forex Friday close: no open positions.")
            return

        logger.info("Forex Friday close: checking %d open positions for weekend profit protection.", len(positions))

        for pos in positions:
            try:
                _maybe_close_for_weekend(pos, session)
            except Exception as exc:
                logger.warning("Forex Friday close error | pair=%s | error=%s", pos.pair, exc)

        session.commit()


def _maybe_close_for_weekend(pos: ForexPosition, session: Session) -> None:
    if not pos.ig_deal_id or not pos.ig_size:
        return

    current_price = get_forex_mid_price(pos.pair)
    pnl, _ = _calculate_pnl(pos, current_price)

    if pnl is None or pnl <= 0:
        logger.info("Forex Friday close: leaving %s %s open (pnl=%s)", pos.pair, pos.direction, pnl)
        return

    logger.info("Forex Friday close: closing %s %s in profit | pnl=£%.2f", pos.pair, pos.direction, pnl)

    try:
        close_ig_position(pos.ig_deal_id, pos.direction, pos.ig_size)
    except Exception as exc:
        logger.warning("Forex Friday close: IG close failed | pair=%s | error=%s", pos.pair, exc)
        return

    pos.status = "closed"
    pos.close_price = current_price
    pos.realised_pnl = pnl
    pos.closed_at = datetime.now(timezone.utc)
    pos.last_assistant_status = "CLOSED"
    pos.last_notified_status = "CLOSED"
    session.add(pos)

    if settings.ENABLE_PUSH_NOTIFICATIONS:
        tokens = session.exec(
            select(DeviceToken).where(DeviceToken.user_id == pos.user_id)
        ).all()
        if tokens:
            send_to_user_devices(
                [t.token for t in tokens],
                title=f"Weekend close: {pos.pair} banked",
                body=f"{pos.direction} {pos.pair} closed before weekend. Profit locked: £{pnl:.2f}.",
                alert_id=pos.id,
                ticker=pos.pair,
                action_strength=100,
            )
