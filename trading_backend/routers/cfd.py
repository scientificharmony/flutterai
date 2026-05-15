from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models.db_models import CfdEntryAlert, User
from models.schemas import CfdEntryAlertResponse, CfdScanRequest, CfdSummaryResponse
from services.cfd_service import get_cfd_summary

router = APIRouter(prefix="/cfd", tags=["cfd"])


@router.get("/summary", response_model=CfdSummaryResponse)
def cfd_summary(_: User = Depends(get_current_user)):
    return get_cfd_summary()


@router.post("/scan", response_model=CfdSummaryResponse)
def cfd_scan(
    body: CfdScanRequest,
    _: User = Depends(get_current_user),
):
    return get_cfd_summary(timeframe=body.timeframe, markets=body.markets or None)


@router.get("/entry-alerts", response_model=list[CfdEntryAlertResponse])
def cfd_entry_alerts(
    limit: int = 10,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    capped_limit = max(1, min(limit, 25))
    alerts = session.exec(
        select(CfdEntryAlert)
        .where(CfdEntryAlert.user_id == user.id)
        .where(CfdEntryAlert.push_sent == True)
        .order_by(CfdEntryAlert.created_at.desc())
        .limit(capped_limit)
    ).all()
    return [
        CfdEntryAlertResponse(
            id=a.id,
            market=a.market,
            epic=a.epic,
            direction=a.direction,
            strength=a.strength,
            timeframe=a.timeframe,
            entry_price=a.entry_price,
            stop_loss=a.stop_loss,
            take_profit=a.take_profit,
            risk_amount=a.risk_amount,
            contract_size=a.contract_size,
            rationale=a.rationale,
            push_sent=a.push_sent,
            created_at=a.created_at,
        )
        for a in alerts
    ]
