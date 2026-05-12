"""
Holdings router.

GET  /holdings              — list all open positions for the current user
POST /holdings              — open a position (called automatically when "took_trade" is recorded)
POST /holdings/{id}/close   — manually close a position (syncs with signal_performance)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models.db_models import OpenPosition, SignalPerformance, User

router = APIRouter(prefix="/holdings", tags=["holdings"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class OpenPositionResponse(BaseModel):
    id: str
    ticker: str
    entry_price: float
    amount: float
    peak_price: Optional[float]
    current_gain_pct: Optional[float]
    status: str
    sell_alert_id: Optional[str]
    opened_at: datetime
    closed_at: Optional[datetime]


class OpenPositionRequest(BaseModel):
    signal_perf_id: str
    ticker: str
    entry_price: float
    amount: float


class ClosePositionRequest(BaseModel):
    pass  # closure is driven by signal_performance update


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(pos: OpenPosition, current_price: Optional[float] = None) -> OpenPositionResponse:
    gain_pct = None
    if current_price and pos.entry_price:
        gain_pct = (current_price - pos.entry_price) / pos.entry_price * 100
    elif pos.peak_price and pos.entry_price:
        gain_pct = (pos.peak_price - pos.entry_price) / pos.entry_price * 100
    return OpenPositionResponse(
        id=pos.id,
        ticker=pos.ticker,
        entry_price=pos.entry_price,
        amount=pos.amount,
        peak_price=pos.peak_price,
        current_gain_pct=round(gain_pct, 2) if gain_pct is not None else None,
        status=pos.status,
        sell_alert_id=pos.sell_alert_id,
        opened_at=pos.opened_at,
        closed_at=pos.closed_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[OpenPositionResponse])
def list_holdings(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    positions = session.exec(
        select(OpenPosition)
        .where(OpenPosition.user_id == user.id)
        .order_by(OpenPosition.opened_at.desc())
    ).all()
    return [_to_response(p) for p in positions]


@router.post("", response_model=OpenPositionResponse)
def open_position(
    body: OpenPositionRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    # Verify the signal_performance belongs to this user
    sp = session.get(SignalPerformance, body.signal_perf_id)
    if not sp or sp.user_id != user.id:
        raise HTTPException(status_code=404, detail="Signal performance record not found.")

    # Don't create duplicates
    existing = session.exec(
        select(OpenPosition).where(OpenPosition.signal_perf_id == body.signal_perf_id)
    ).first()
    if existing:
        return _to_response(existing)

    pos = OpenPosition(
        user_id=user.id,
        signal_perf_id=body.signal_perf_id,
        ticker=body.ticker,
        entry_price=body.entry_price,
        amount=body.amount,
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return _to_response(pos)


@router.post("/{position_id}/close", response_model=OpenPositionResponse)
def close_position(
    position_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pos = session.get(OpenPosition, position_id)
    if not pos or pos.user_id != user.id:
        raise HTTPException(status_code=404, detail="Position not found.")
    if pos.status == "closed":
        return _to_response(pos)

    pos.status = "closed"
    pos.closed_at = datetime.now(timezone.utc)
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return _to_response(pos)
