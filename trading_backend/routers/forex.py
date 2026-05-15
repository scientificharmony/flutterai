from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from auth import get_current_user
from config import settings
from database import get_session
from models.db_models import ForexEntryAlert, ForexPosition, User
from models.schemas import ForexEntryAlertResponse, ForexScanRequest, ForexSummaryResponse
from routers.forex_positions import ForexPositionResponse, _to_response
from services.forex_service import find_matching_ig_position, get_forex_mid_price, get_forex_summary, place_ig_demo_position

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forex", tags=["forex"])

class ForexExecuteCustomBody(BaseModel):
    size: float = Field(..., gt=0, le=50)
    stop_loss: float
    take_profit: float


@router.get("/summary", response_model=ForexSummaryResponse)
def forex_summary(_: User = Depends(get_current_user)):
    return get_forex_summary()


@router.post("/scan", response_model=ForexSummaryResponse)
def forex_scan(
    body: ForexScanRequest,
    _: User = Depends(get_current_user),
):
    return get_forex_summary(timeframe=body.timeframe, pairs=body.pairs or None)


@router.get("/entry-alerts", response_model=list[ForexEntryAlertResponse])
def forex_entry_alerts(
    limit: int = 10,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    capped_limit = max(1, min(limit, 25))
    alerts = session.exec(
        select(ForexEntryAlert)
        .where(ForexEntryAlert.user_id == user.id)
        .where(ForexEntryAlert.push_sent == True)
        .order_by(ForexEntryAlert.created_at.desc())
        .limit(capped_limit)
    ).all()
    open_positions = session.exec(
        select(ForexPosition.pair, ForexPosition.direction)
        .where(ForexPosition.user_id == user.id)
        .where(ForexPosition.status == "open")
    ).all()
    tracked_pairs = {(pair, direction) for pair, direction in open_positions}
    return [
        ForexEntryAlertResponse(
            id=alert.id,
            pair=alert.pair,
            direction=alert.direction,
            strength=alert.strength,
            timeframe=alert.timeframe,
            entry_price=alert.entry_price,
            stop_loss=alert.stop_loss,
            take_profit=alert.take_profit,
            risk_amount=alert.risk_amount,
            position_units=alert.position_units,
            rationale=alert.rationale,
            push_sent=alert.push_sent,
            tracked=(alert.pair, alert.direction) in tracked_pairs,
            declined=alert.declined,
            created_at=alert.created_at,
        )
        for alert in alerts
    ]


@router.get("/entry-alerts/{alert_id}", response_model=ForexEntryAlertResponse)
def get_forex_entry_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.get(ForexEntryAlert, alert_id)
    if not alert or alert.user_id != user.id or not alert.push_sent:
        raise HTTPException(status_code=404, detail="Forex entry alert not found.")
    tracked = session.exec(
        select(ForexPosition)
        .where(
            ForexPosition.user_id == user.id,
            ForexPosition.pair == alert.pair,
            ForexPosition.direction == alert.direction,
            ForexPosition.status == "open",
        )
    ).first() is not None
    return ForexEntryAlertResponse(
        id=alert.id,
        pair=alert.pair,
        direction=alert.direction,
        strength=alert.strength,
        timeframe=alert.timeframe,
        entry_price=alert.entry_price,
        stop_loss=alert.stop_loss,
        take_profit=alert.take_profit,
        risk_amount=alert.risk_amount,
        position_units=alert.position_units,
        rationale=alert.rationale,
        push_sent=alert.push_sent,
        tracked=tracked,
        declined=alert.declined,
        created_at=alert.created_at,
    )


@router.post("/entry-alerts/{alert_id}/decline")
def decline_forex_entry_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.get(ForexEntryAlert, alert_id)
    if not alert or alert.user_id != user.id or not alert.push_sent:
        raise HTTPException(status_code=404, detail="Forex entry alert not found.")
    alert.declined = True
    alert.declined_at = datetime.now(timezone.utc)
    session.add(alert)
    session.commit()
    return {"status": "ok"}


@router.post("/entry-alerts/{alert_id}/execute-demo", response_model=ForexPositionResponse)
def execute_forex_entry_alert_demo(
    alert_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if settings.IG_ACCOUNT_TYPE.upper() != "DEMO":
        raise HTTPException(status_code=403, detail="Forex execution is only enabled for IG DEMO accounts.")
    if settings.FOREX_PROVIDER.lower() != "ig":
        raise HTTPException(status_code=422, detail="IG forex provider is not configured.")

    alert = session.get(ForexEntryAlert, alert_id)
    if not alert or alert.user_id != user.id or not alert.push_sent:
        raise HTTPException(status_code=404, detail="Forex entry alert not found.")
    if alert.direction not in {"LONG", "SHORT"}:
        raise HTTPException(status_code=422, detail="Only LONG or SHORT alerts can be executed.")

    existing = session.exec(
        select(ForexPosition).where(
            ForexPosition.user_id == user.id,
            ForexPosition.pair == alert.pair,
            ForexPosition.direction == alert.direction,
            ForexPosition.status == "open",
        )
    ).first()
    if existing:
        return _to_response(existing, get_forex_mid_price(existing.pair))

    current_price = get_forex_mid_price(alert.pair)
    if current_price is None:
        raise HTTPException(status_code=422, detail="Current IG price is unavailable.")
    max_slippage = settings.FOREX_EXECUTION_MAX_SLIPPAGE_PIPS * _pip_size(alert.pair)
    if abs(current_price - alert.entry_price) > max_slippage:
        raise HTTPException(
            status_code=409,
            detail="Market moved too far from the alert entry. Refresh and wait for a new setup.",
        )

    placed = place_ig_demo_position(
        pair=alert.pair,
        direction=alert.direction,
        size=settings.FOREX_IG_DEMO_SIZE,
        stop_level=alert.stop_loss,
        limit_level=alert.take_profit,
    )
    deal_id = placed.deal_id
    if not deal_id:
        # Confirm endpoint can lag; fall back to the most recent matching open position.
        try:
            matched = find_matching_ig_position(alert.pair, alert.direction)
        except Exception:
            matched = None
        if matched:
            deal_id = matched.deal_id
    pos = ForexPosition(
        user_id=user.id,
        pair=alert.pair,
        direction=alert.direction,
        entry_price=current_price,
        stop_loss=alert.stop_loss,
        take_profit=alert.take_profit,
        risk_amount=alert.risk_amount,
        position_units=alert.position_units,
        timeframe=alert.timeframe,
        ig_deal_id=deal_id or placed.deal_reference,
        ig_epic=placed.epic,
        ig_size=placed.size,
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return _to_response(pos, get_forex_mid_price(pos.pair))


@router.post("/entry-alerts/{alert_id}/execute-demo-custom", response_model=ForexPositionResponse)
def execute_forex_entry_alert_demo_custom(
    alert_id: str,
    body: ForexExecuteCustomBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    logger.info("FOREX EXECUTE START | user=%s | alert=%s", user.id, alert_id)

    if settings.IG_ACCOUNT_TYPE.upper() != "DEMO":
        raise HTTPException(status_code=403, detail="Forex execution is only enabled for IG DEMO accounts.")
    if settings.FOREX_PROVIDER.lower() != "ig":
        raise HTTPException(status_code=422, detail="IG forex provider is not configured.")

    logger.info("FOREX EXECUTE | provider=%s | account_type=%s | ig_user=%s",
                 settings.FOREX_PROVIDER, settings.IG_ACCOUNT_TYPE, settings.IG_USERNAME)

    alert = session.get(ForexEntryAlert, alert_id)
    if not alert or alert.user_id != user.id or not alert.push_sent:
        raise HTTPException(status_code=404, detail="Forex entry alert not found.")
    if alert.direction not in {"LONG", "SHORT"}:
        raise HTTPException(status_code=422, detail="Only LONG or SHORT alerts can be executed.")

    logger.info("FOREX EXECUTE | pair=%s | direction=%s | entry=%.5f | stop=%.5f | tp=%.5f",
                 alert.pair, alert.direction, alert.entry_price, alert.stop_loss, alert.take_profit)

    if body.stop_loss == body.take_profit:
        raise HTTPException(status_code=422, detail="Stop and target cannot be the same.")

    # Reuse existing open position if already tracked for this (pair,direction)
    existing = session.exec(
        select(ForexPosition).where(
            ForexPosition.user_id == user.id,
            ForexPosition.pair == alert.pair,
            ForexPosition.direction == alert.direction,
            ForexPosition.status == "open",
        )
    ).first()
    if existing:
        logger.info("FOREX EXECUTE | reusing existing open position | pos=%s", existing.id)
        return _to_response(existing, get_forex_mid_price(existing.pair))

    current_price = get_forex_mid_price(alert.pair)
    if current_price is None:
        logger.warning("FOREX EXECUTE | current IG price unavailable for %s", alert.pair)
        raise HTTPException(status_code=422, detail="Current IG price is unavailable.")

    logger.info("FOREX EXECUTE | current_price=%.5f | alert_entry=%.5f", current_price, alert.entry_price)

    max_slippage = settings.FOREX_EXECUTION_MAX_SLIPPAGE_PIPS * _pip_size(alert.pair)
    if abs(current_price - alert.entry_price) > max_slippage:
        logger.warning("FOREX EXECUTE | slippage exceeded | delta=%.5f | max=%.5f",
                       abs(current_price - alert.entry_price), max_slippage)
        raise HTTPException(
            status_code=409,
            detail="Market moved too far from the alert entry. Refresh and wait for a new setup.",
        )

    try:
        placed = place_ig_demo_position(
            pair=alert.pair,
            direction=alert.direction,
            size=body.size,
            stop_level=body.stop_loss,
            limit_level=body.take_profit,
        )
    except Exception as exc:
        logger.error("FOREX EXECUTE | IG placement failed | pair=%s | direction=%s | error=%s",
                     alert.pair, alert.direction, exc)
        raise HTTPException(
            status_code=422,
            detail=f"IG demo trade placement failed: {exc}",
        )

    logger.info("FOREX EXECUTE | IG placed | deal_id=%s | deal_ref=%s | epic=%s | size=%s",
                 placed.deal_id, placed.deal_reference, placed.epic, placed.size)

    deal_id = placed.deal_id
    if not deal_id:
        try:
            matched = find_matching_ig_position(alert.pair, alert.direction)
        except Exception:
            matched = None
        if matched:
            deal_id = matched.deal_id
            logger.info("FOREX EXECUTE | deal_id resolved via position match | deal_id=%s", deal_id)

    pos = ForexPosition(
        user_id=user.id,
        pair=alert.pair,
        direction=alert.direction,
        entry_price=current_price,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        risk_amount=alert.risk_amount,
        position_units=alert.position_units,
        timeframe=alert.timeframe,
        ig_deal_id=deal_id or placed.deal_reference,
        ig_epic=placed.epic,
        ig_size=placed.size,
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)

    logger.info("FOREX EXECUTE COMPLETE | pos=%s | ig_deal_id=%s", pos.id, deal_id or placed.deal_reference)
    return _to_response(pos, get_forex_mid_price(pos.pair))


def _pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("/JPY") else 0.0001
