from fastapi import APIRouter, Depends
from sqlmodel import Session, select, join

from auth import require_admin
from database import get_session
from models.db_models import TradeAlert, AlertOutcome
from models.schemas import StrategyPerformanceRow

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/strategy-performance", response_model=list[StrategyPerformanceRow])
def strategy_performance(
    limit: int = 100,
    _: bool = Depends(require_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(TradeAlert, AlertOutcome)
        .join(AlertOutcome, AlertOutcome.alert_id == TradeAlert.id, isouter=True)
        .order_by(TradeAlert.created_at.desc())
        .limit(limit)
    ).all()

    results = []
    for alert, outcome in rows:
        results.append(
            StrategyPerformanceRow(
                ticker=alert.ticker,
                action=alert.action,
                signal_score=alert.signal_score,
                confidence=alert.confidence,
                suggested_amount=alert.suggested_amount,
                price_at_alert=alert.price_at_alert,
                price_1h=outcome.price_1h if outcome else None,
                price_4h=outcome.price_4h if outcome else None,
                price_1d=outcome.price_1d if outcome else None,
                price_5d=outcome.price_5d if outcome else None,
                max_gain=outcome.max_gain if outcome else None,
                max_drawdown=outcome.max_drawdown if outcome else None,
                created_at=alert.created_at,
            )
        )
    return results
