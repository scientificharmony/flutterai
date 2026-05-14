from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from config import settings
from database import get_session
from models.db_models import ForexEntryAlert, ForexPosition, User
from models.schemas import ForexEntryAlertResponse, ForexScanRequest, ForexSummaryResponse
from routers.forex_positions import ForexPositionResponse, _to_response
from services.forex_service import get_forex_mid_price, get_forex_summary, place_ig_demo_position

router = APIRouter(prefix="/forex", tags=["forex"])


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
            created_at=alert.created_at,
        )
        for alert in alerts
    ]


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
        ig_deal_id=placed.deal_id or placed.deal_reference,
        ig_epic=placed.epic,
        ig_size=placed.size,
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return _to_response(pos, get_forex_mid_price(pos.pair))


def _pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("/JPY") else 0.0001
