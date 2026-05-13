"""
Private test dashboard — GET /test/performance-summary
Only accessible in APP_MODE=private_test.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from config import settings
from database import get_session
from models.db_models import DeviceToken, OpenPosition, SignalPerformance, Strategy, User, UserSettings
from models.schemas import (
    DailyUsageSummary,
    PerformanceSummary,
    SignalPerformanceResponse,
)
from services.budget_service import get_or_create_usage, budget_remaining

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["test-dashboard"])


def _quiet_hours_active(user_settings: UserSettings | None) -> bool:
    start = user_settings.quiet_hours_start if user_settings else settings.quiet_hours_start
    end = user_settings.quiet_hours_end if user_settings else settings.quiet_hours_end
    hour = datetime.now(timezone.utc).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


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


@router.get("/performance-summary", response_model=PerformanceSummary)
def performance_summary(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not settings.is_private_test:
        raise HTTPException(status_code=403, detail="Dashboard only available in private_test mode.")

    all_perfs = session.exec(
        select(SignalPerformance)
        .where(SignalPerformance.user_id == user.id)
        .order_by(SignalPerformance.created_at.desc())
    ).all()

    total_alerts = len(all_perfs)
    took_trade = sum(1 for p in all_perfs if p.outcome == "took_trade")
    ignored = sum(1 for p in all_perfs if p.outcome == "ignored")
    watching = sum(1 for p in all_perfs if p.outcome == "watching")
    unrecorded = total_alerts - took_trade - ignored - watching

    # Win rate: among closed trades where we know exit price
    closed = [p for p in all_perfs if p.outcome == "took_trade" and p.realised_pnl is not None]
    win_rate = None
    if closed:
        wins = sum(1 for p in closed if (p.realised_pnl or 0) > 0)
        win_rate = round(wins / len(closed) * 100, 1)

    # Average price change at 1d and 5d
    def _avg_pct(prices: list[float | None], baselines: list[float]) -> float | None:
        pairs = [(p, b) for p, b in zip(prices, baselines) if p is not None and b > 0]
        if not pairs:
            return None
        return round(sum((p - b) / b * 100 for p, b in pairs) / len(pairs), 2)

    avg_1d = _avg_pct([p.price_1d for p in all_perfs], [p.price_at_alert for p in all_perfs])
    avg_4h = _avg_pct([p.price_4h for p in all_perfs], [p.price_at_alert for p in all_perfs])
    avg_5d = _avg_pct([p.price_5d for p in all_perfs], [p.price_at_alert for p in all_perfs])
    avg_1h = _avg_pct([p.price_1h for p in all_perfs], [p.price_at_alert for p in all_perfs])

    total_realised_pnl = round(sum(p.realised_pnl or 0.0 for p in all_perfs), 4)
    est_claude_cost = round(sum(p.claude_cost_estimate for p in all_perfs), 4)
    est_mkt_cost = round(sum(p.market_data_cost_estimate for p in all_perfs), 4)
    net = round(total_realised_pnl - est_claude_cost - est_mkt_cost, 4)
    acted = _avg_pct(
        [p.price_1d for p in all_perfs if p.outcome == "took_trade"],
        [p.price_at_alert for p in all_perfs if p.outcome == "took_trade"],
    )
    ignored_result = _avg_pct(
        [p.price_1d for p in all_perfs if p.outcome == "ignored"],
        [p.price_at_alert for p in all_perfs if p.outcome == "ignored"],
    )
    bands = ["0-29", "30-49", "50-69", "70-84", "85-100"]
    by_band: dict[str, list[SignalPerformance]] = {b: [] for b in bands}
    for p in all_perfs:
        s = p.action_strength
        key = "0-29" if s <= 29 else "30-49" if s <= 49 else "50-69" if s <= 69 else "70-84" if s <= 84 else "85-100"
        by_band[key].append(p)
    band_scores: dict[str, float] = {}
    api_cost_per_band: dict[str, float] = {}
    for band, items in by_band.items():
        if items:
            vals = [((p.price_1d - p.price_at_alert) / p.price_at_alert * 100) for p in items if p.price_1d is not None and p.price_at_alert > 0]
            if vals:
                band_scores[band] = round(sum(vals) / len(vals), 2)
            api_cost_per_band[band] = round(sum((p.claude_cost_estimate + p.market_data_cost_estimate) for p in items), 4)
        else:
            api_cost_per_band[band] = 0.0
    best_band = max(band_scores, key=band_scores.get) if band_scores else None
    worst_band = min(band_scores, key=band_scores.get) if band_scores else None

    # Today's usage
    today_usage_row = get_or_create_usage(user.id, session)
    rem = budget_remaining(user.id, session)
    today_usage = DailyUsageSummary(
        date=today_usage_row.date,
        claude_calls=today_usage_row.claude_calls,
        estimated_cost_gbp=round(today_usage_row.estimated_cost_gbp, 4),
        market_data_calls=today_usage_row.market_data_calls,
        alerts_sent=today_usage_row.alerts_sent,
        budget_remaining_gbp=round(rem, 4),
    )

    recent = [_perf_to_response(p) for p in all_perfs[:20]]

    return PerformanceSummary(
        total_alerts=total_alerts,
        took_trade=took_trade,
        ignored=ignored,
        watching=watching,
        unrecorded=unrecorded,
        win_rate_pct=win_rate,
        avg_1d_pct=avg_1d,
        avg_5d_pct=avg_5d,
        average_1h_result=avg_1h,
        average_4h_result=avg_4h,
        average_1d_result=avg_1d,
        average_5d_result=avg_5d,
        acted_on_result=acted,
        ignored_result=ignored_result,
        api_cost_per_band=api_cost_per_band,
        best_performing_action_strength_band=best_band,
        worst_performing_action_strength_band=worst_band,
        total_realised_pnl=total_realised_pnl,
        estimated_claude_cost_gbp=est_claude_cost,
        estimated_market_data_cost_gbp=est_mkt_cost,
        net_after_api_costs=net,
        today_usage=today_usage,
        recent_signals=recent,
    )


@router.get("/notification-diagnostics")
def notification_diagnostics(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if not settings.is_private_test:
        raise HTTPException(status_code=403, detail="Diagnostics only available in private_test mode.")

    strategies = session.exec(
        select(Strategy).where(Strategy.user_id == user.id)
    ).all()
    enabled_strategies = [strategy for strategy in strategies if strategy.enabled]
    tokens = session.exec(
        select(DeviceToken).where(DeviceToken.user_id == user.id)
    ).all()
    user_settings = session.exec(
        select(UserSettings).where(UserSettings.user_id == user.id)
    ).first()
    open_positions = session.exec(
        select(OpenPosition).where(
            OpenPosition.user_id == user.id,
            OpenPosition.status == "open",
        )
    ).all()
    today_usage = get_or_create_usage(user.id, session)

    return {
        "push_enabled": settings.ENABLE_PUSH_NOTIFICATIONS,
        "firebase_credentials_configured": bool(settings.FIREBASE_SERVICE_ACCOUNT_PATH),
        "registered_device_tokens": len(tokens),
        "quiet_hours_active": _quiet_hours_active(user_settings),
        "quiet_hours_start_utc": user_settings.quiet_hours_start if user_settings else settings.quiet_hours_start,
        "quiet_hours_end_utc": user_settings.quiet_hours_end if user_settings else settings.quiet_hours_end,
        "strategies_total": len(strategies),
        "strategies_enabled": len(enabled_strategies),
        "enabled_strategy_ids": [strategy.id for strategy in enabled_strategies],
        "enabled_strategy_watchlists": {
            strategy.id: strategy.watchlist for strategy in enabled_strategies
        },
        "open_positions": len(open_positions),
        "today_claude_calls": today_usage.claude_calls,
        "today_alerts_sent": today_usage.alerts_sent,
        "daily_alert_limit": settings.MAX_ALERTS_PER_DAY,
        "min_push_action_strength": settings.MIN_PUSH_ACTION_STRENGTH,
    }
