from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models.db_models import ForexEntryAlert, ForexPosition, User
from models.schemas import ForexEntryAlertResponse, ForexScanRequest, ForexSummaryResponse
from services.forex_service import get_forex_summary

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
