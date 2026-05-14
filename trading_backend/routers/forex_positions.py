from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models.db_models import ForexPosition, User
from services.forex_service import (
    find_matching_ig_position,
    get_forex_mid_price,
    get_ig_open_positions,
    infer_pair_from_ig_position,
)

router = APIRouter(prefix="/forex/positions", tags=["forex"])


class ForexPositionRequest(BaseModel):
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    position_units: int = Field(default=0, ge=0)
    timeframe: str = "15m"


class CloseForexPositionRequest(BaseModel):
    close_price: Optional[float] = None


class ForexPositionResponse(BaseModel):
    id: str
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    position_units: int
    timeframe: str
    status: str
    ig_linked: bool
    ig_deal_id: Optional[str] = None
    ig_size: Optional[float] = None
    current_price: Optional[float]
    current_pnl: Optional[float]
    current_pnl_pct: Optional[float]
    assistant_status: str
    assistant_message: str
    close_price: Optional[float]
    realised_pnl: Optional[float]
    opened_at: datetime
    closed_at: Optional[datetime]


def _calculate_pnl(pos: ForexPosition, price: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    if price is None or pos.entry_price == 0 or pos.position_units <= 0:
        return None, None
    multiplier = 1 if pos.direction == "LONG" else -1
    pnl = (price - pos.entry_price) * pos.position_units * multiplier
    pnl_pct = (price - pos.entry_price) / pos.entry_price * 100 * multiplier
    return round(pnl, 2), round(pnl_pct, 3)


def assistant_guidance(pos: ForexPosition, price: Optional[float], pnl: Optional[float]) -> tuple[str, str]:
    if pos.status == "closed":
        return "CLOSED", "Practice trade is closed and realised P/L has been recorded."
    if price is None:
        return "WAIT", "Current IG price is unavailable. Do not act until price refreshes."

    if pos.direction == "LONG":
        hit_target = price >= pos.take_profit
        hit_stop = price <= pos.stop_loss
        target_progress = (price - pos.entry_price) / max(pos.take_profit - pos.entry_price, 0.0000001)
    else:
        hit_target = price <= pos.take_profit
        hit_stop = price >= pos.stop_loss
        target_progress = (pos.entry_price - price) / max(pos.entry_price - pos.take_profit, 0.0000001)

    if hit_target:
        return "TAKE_PROFIT", "Target reached. Consider closing the practice trade and banking the gain."
    if hit_stop:
        return "CUT_LOSS", "Stop reached. The trade idea is invalid; close or review immediately."
    if pnl is not None and pnl > 0 and target_progress >= 0.6:
        return "PROTECT_PROFIT", "Trade is well in profit. Watch for reversal or consider locking some gain."
    if pnl is not None and pnl < 0:
        return "HOLD_CAUTION", "Trade is currently against you but has not reached stop."
    return "HOLD", "Trade is active. Hold while price remains between stop and target."


def _to_response(pos: ForexPosition, current_price: Optional[float] = None) -> ForexPositionResponse:
    price = current_price if pos.status == "open" else pos.close_price
    pnl, pnl_pct = _calculate_pnl(pos, price)
    assistant_status, assistant_message = assistant_guidance(pos, price, pnl)
    return ForexPositionResponse(
        id=pos.id,
        pair=pos.pair,
        direction=pos.direction,
        entry_price=pos.entry_price,
        stop_loss=pos.stop_loss,
        take_profit=pos.take_profit,
        risk_amount=pos.risk_amount,
        position_units=pos.position_units,
        timeframe=pos.timeframe,
        status=pos.status,
        ig_linked=bool(pos.ig_deal_id),
        ig_deal_id=pos.ig_deal_id,
        ig_size=pos.ig_size,
        current_price=round(price, 5) if price is not None else None,
        current_pnl=pnl,
        current_pnl_pct=pnl_pct,
        assistant_status=assistant_status,
        assistant_message=assistant_message,
        close_price=pos.close_price,
        realised_pnl=pos.realised_pnl,
        opened_at=pos.opened_at,
        closed_at=pos.closed_at,
    )


def _link_unlinked_ig_positions(positions: list[ForexPosition], session: Session) -> None:
    linked_deal_ids = {pos.ig_deal_id for pos in positions if pos.ig_deal_id}
    changed = False
    for pos in positions:
        if pos.status != "open" or pos.ig_deal_id:
            continue
        try:
            ig_position = find_matching_ig_position(pos.pair, pos.direction, linked_deal_ids)
        except Exception:
            ig_position = None
        if not ig_position:
            continue
        pos.ig_deal_id = ig_position.deal_id
        pos.ig_epic = ig_position.epic
        pos.ig_size = ig_position.size
        linked_deal_ids.add(ig_position.deal_id)
        session.add(pos)
        changed = True
    if changed:
        session.commit()


def _sync_missing_ig_positions(user: User, session: Session) -> None:
    """
    If the user manually opens positions on IG (or accidentally closes a trade in-app),
    our DB can miss those open IG positions. This imports any IG-open positions that
    don't already exist in the DB by dealId.
    """
    try:
        ig_positions = get_ig_open_positions()
    except Exception:
        return
    if not ig_positions:
        return

    rows = session.exec(
        select(ForexPosition.ig_deal_id)
        .where(ForexPosition.user_id == user.id)
        .where(ForexPosition.status == "open")
        .where(ForexPosition.ig_deal_id != None)
    ).all()
    existing_open_deals = {row for row in rows if row}

    changed = False
    for ig in ig_positions:
        if ig.deal_id in existing_open_deals:
            continue

        existing = session.exec(
            select(ForexPosition)
            .where(ForexPosition.user_id == user.id)
            .where(ForexPosition.ig_deal_id == ig.deal_id)
            .order_by(ForexPosition.opened_at.desc())
        ).first()
        if existing:
            pair = infer_pair_from_ig_position(ig.epic, ig.instrument_name) or existing.pair
            direction = "LONG" if ig.direction.upper() == "BUY" else "SHORT"
            entry = ig.level if ig.level is not None else (get_forex_mid_price(pair) or existing.entry_price)
            stop = ig.stop_level if ig.stop_level is not None else existing.stop_loss
            limit = ig.limit_level if ig.limit_level is not None else existing.take_profit

            existing.status = "open"
            existing.pair = pair
            existing.direction = direction
            existing.entry_price = float(entry)
            existing.stop_loss = float(stop)
            existing.take_profit = float(limit)
            existing.close_price = None
            existing.realised_pnl = None
            existing.closed_at = None
            existing.ig_epic = ig.epic
            existing.ig_size = ig.size

            session.add(existing)
            existing_open_deals.add(ig.deal_id)
            changed = True
            continue

        pair = infer_pair_from_ig_position(ig.epic, ig.instrument_name)
        if not pair:
            continue
        direction = "LONG" if ig.direction.upper() == "BUY" else "SHORT"
        entry = ig.level if ig.level is not None else (get_forex_mid_price(pair) or 0.0)
        stop = ig.stop_level if ig.stop_level is not None else entry
        limit = ig.limit_level if ig.limit_level is not None else entry
        pos = ForexPosition(
            user_id=user.id,
            pair=pair,
            direction=direction,
            entry_price=float(entry),
            stop_loss=float(stop),
            take_profit=float(limit),
            risk_amount=0.0,
            position_units=0,
            timeframe="15m",
            status="open",
            ig_deal_id=ig.deal_id,
            ig_epic=ig.epic,
            ig_size=ig.size,
        )
        session.add(pos)
        existing_open_deals.add(ig.deal_id)
        changed = True

    if changed:
        session.commit()


@router.get("", response_model=list[ForexPositionResponse])
def list_forex_positions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _sync_missing_ig_positions(user, session)
    positions = session.exec(
        select(ForexPosition)
        .where(ForexPosition.user_id == user.id)
        .order_by(ForexPosition.opened_at.desc())
    ).all()
    _link_unlinked_ig_positions(positions, session)
    current_prices = {pos.pair: get_forex_mid_price(pos.pair) for pos in positions if pos.status == "open"}
    return [_to_response(pos, current_prices.get(pos.pair)) for pos in positions]


@router.post("", response_model=ForexPositionResponse)
def open_forex_position(
    body: ForexPositionRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    direction = body.direction.upper()
    if direction not in {"LONG", "SHORT"}:
        raise HTTPException(status_code=422, detail="direction must be LONG or SHORT.")

    ig_position = None
    try:
        used_deal_ids = set(
            session.exec(
                select(ForexPosition.ig_deal_id).where(ForexPosition.ig_deal_id != None)
            ).all()
        )
        ig_position = find_matching_ig_position(body.pair, direction, used_deal_ids)
    except Exception:
        ig_position = None

    pos = ForexPosition(
        user_id=user.id,
        pair=body.pair,
        direction=direction,
        entry_price=body.entry_price,
        stop_loss=body.stop_loss,
        take_profit=body.take_profit,
        risk_amount=body.risk_amount,
        position_units=body.position_units,
        timeframe=body.timeframe,
        ig_deal_id=ig_position.deal_id if ig_position else None,
        ig_epic=ig_position.epic if ig_position else None,
        ig_size=ig_position.size if ig_position else None,
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return _to_response(pos, get_forex_mid_price(pos.pair))


@router.post("/{position_id}/close", response_model=ForexPositionResponse)
def close_forex_position(
    position_id: str,
    body: CloseForexPositionRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    pos = session.get(ForexPosition, position_id)
    if not pos or pos.user_id != user.id:
        raise HTTPException(status_code=404, detail="Forex position not found.")
    if pos.status == "closed":
        return _to_response(pos)

    close_price = body.close_price or get_forex_mid_price(pos.pair)
    if close_price is None:
        raise HTTPException(status_code=422, detail="Close price unavailable.")

    realised_pnl, _ = _calculate_pnl(pos, close_price)
    pos.status = "closed"
    pos.close_price = close_price
    pos.realised_pnl = realised_pnl
    pos.closed_at = datetime.now(timezone.utc)
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return _to_response(pos)
