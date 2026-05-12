from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models.db_models import User, TradeAlert, SignalPerformance
from models.schemas import (
    TradeAlertResponse,
    RecordOutcomeRequest,
    CloseTradeRequest,
    SignalPerformanceResponse,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _to_response(alert: TradeAlert) -> TradeAlertResponse:
    return TradeAlertResponse(
        id=alert.id,
        ticker=alert.ticker,
        action=alert.action,
        signal_score=alert.signal_score,
        confidence=alert.confidence,
        formula_score=alert.formula_score,
        claude_confidence=alert.claude_confidence,
        portfolio_fit_score=alert.portfolio_fit_score,
        weakness_score=alert.weakness_score,
        drawdown_risk_score=alert.drawdown_risk_score,
        exposure_risk_score=alert.exposure_risk_score,
        action_strength=alert.action_strength,
        action_label=alert.action_label,
        score_interpretation=alert.score_interpretation,
        action_strength_disclaimer=alert.action_strength_disclaimer,
        trading212_review_enabled=alert.trading212_review_enabled,
        suggested_amount=alert.suggested_amount,
        price_at_alert=alert.price_at_alert,
        alert_title=alert.alert_title,
        alert_body=alert.alert_body,
        rationale=alert.rationale,
        risk_note=alert.risk_note,
        key_factors=alert.key_factors,
        blocking_risks=alert.blocking_risks,
        expires_at=alert.expires_at,
        executable=alert.executable,
        safety_flags=alert.safety_flags,
        created_at=alert.created_at,
    )


@router.get("", response_model=list[TradeAlertResponse])
def list_alerts(
    limit: int = 20,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alerts = session.exec(
        select(TradeAlert)
        .where(TradeAlert.user_id == user.id)
        .order_by(TradeAlert.created_at.desc())
        .limit(limit)
    ).all()
    return [_to_response(a) for a in alerts]


@router.get("/{alert_id}", response_model=TradeAlertResponse)
def get_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.exec(
        select(TradeAlert).where(
            TradeAlert.id == alert_id, TradeAlert.user_id == user.id
        )
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return _to_response(alert)


# ── Trade outcome endpoints ───────────────────────────────────────────────────

def _perf_to_response(p: SignalPerformance) -> SignalPerformanceResponse:
    return SignalPerformanceResponse(
        alert_id=p.alert_id,
        ticker=p.ticker,
        action=p.action,
        formula_score=p.formula_score,
        claude_confidence=p.claude_confidence,
        action_strength=p.action_strength,
        action_label=p.action_label,
        price_at_alert=p.price_at_alert,
        suggested_amount=p.suggested_amount,
        outcome=p.outcome,
        manual_entry_price=p.manual_entry_price,
        manual_exit_price=p.manual_exit_price,
        manual_amount=p.manual_amount,
        realised_pnl=p.realised_pnl,
        trade_notes=p.trade_notes,
        price_1h=p.price_1h,
        price_4h=p.price_4h,
        price_1d=p.price_1d,
        price_5d=p.price_5d,
        max_gain_1d=p.max_gain_1d,
        max_drawdown_1d=p.max_drawdown_1d,
        claude_cost_estimate=p.claude_cost_estimate,
        created_at=p.created_at,
    )


@router.post("/{alert_id}/outcome", response_model=SignalPerformanceResponse)
def record_outcome(
    alert_id: str,
    body: RecordOutcomeRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.exec(
        select(TradeAlert).where(TradeAlert.id == alert_id, TradeAlert.user_id == user.id)
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    perf = session.exec(
        select(SignalPerformance).where(
            SignalPerformance.alert_id == alert_id,
            SignalPerformance.user_id == user.id,
        )
    ).first()
    if not perf:
        perf = SignalPerformance(
            user_id=user.id,
            alert_id=alert_id,
            ticker=alert.ticker,
            action=alert.action,
            formula_score=alert.signal_score,
            claude_confidence=alert.confidence,
            action_strength=alert.action_strength,
            action_label=alert.action_label,
            price_at_alert=alert.price_at_alert,
            suggested_amount=alert.suggested_amount,
        )

    perf.outcome = body.outcome
    perf.updated_at = datetime.now(timezone.utc)
    if body.outcome == "took_trade":
        if body.manual_entry_price is not None:
            perf.manual_entry_price = body.manual_entry_price
        if body.manual_amount is not None:
            perf.manual_amount = body.manual_amount
    if body.trade_notes is not None:
        perf.trade_notes = body.trade_notes

    session.add(perf)
    session.commit()
    session.refresh(perf)
    return _perf_to_response(perf)


@router.patch("/{alert_id}/outcome/close", response_model=SignalPerformanceResponse)
def close_trade(
    alert_id: str,
    body: CloseTradeRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.exec(
        select(TradeAlert).where(TradeAlert.id == alert_id, TradeAlert.user_id == user.id)
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    perf = session.exec(
        select(SignalPerformance).where(
            SignalPerformance.alert_id == alert_id,
            SignalPerformance.user_id == user.id,
        )
    ).first()
    if not perf:
        raise HTTPException(status_code=404, detail="No performance record for this alert.")
    if perf.outcome != "took_trade":
        raise HTTPException(status_code=422, detail="Can only close a trade marked as took_trade.")

    perf.manual_exit_price = body.manual_exit_price
    if body.realised_pnl is not None:
        perf.realised_pnl = body.realised_pnl
    elif perf.manual_entry_price and perf.manual_amount:
        shares = perf.manual_amount / perf.manual_entry_price
        perf.realised_pnl = round((body.manual_exit_price - perf.manual_entry_price) * shares, 4)
    if body.trade_notes:
        perf.trade_notes = body.trade_notes
    perf.updated_at = datetime.now(timezone.utc)

    session.add(perf)
    session.commit()
    session.refresh(perf)
    return _perf_to_response(perf)


@router.get("/{alert_id}/outcome", response_model=SignalPerformanceResponse)
def get_outcome(
    alert_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    alert = session.exec(
        select(TradeAlert).where(TradeAlert.id == alert_id, TradeAlert.user_id == user.id)
    ).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    perf = session.exec(
        select(SignalPerformance).where(
            SignalPerformance.alert_id == alert_id,
            SignalPerformance.user_id == user.id,
        )
    ).first()
    if not perf:
        raise HTTPException(status_code=404, detail="No performance record for this alert.")
    return _perf_to_response(perf)
