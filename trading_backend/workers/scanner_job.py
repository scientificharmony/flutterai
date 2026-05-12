"""
Scheduled market scan job.
Runs per-strategy, respects plan limits, market hours, quiet hours,
and duplicate ticker cooldown.

Mirrors the manual_scan Action Strength pipeline:
- Formula engine scores candidates.
- Claude only explains/ranks validated Invest candidates.
- Backend calculates Action Strength and decides BUY_REVIEW vs WATCH/DO_NOT_ACT.
- No automatic trades. No order execution.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from config import settings
from database import engine
from models.db_models import (
    User, UserSettings, Strategy, TradeAlert,
    ScanUsage, AlertOutcome, DeviceToken, SignalPerformance,
)
from models.schemas import (
    ACTION_STRENGTH_DISCLAIMER,
    interpretation_for_score,
    label_for_action_strength,
)
from services import trading212_service, claude_service
from services.action_strength_engine import calculate_buy_action_strength
from services.budget_service import can_call_claude, can_send_alert, record_claude_call, record_alert_sent
from services.formula_engine import scan_watchlist
from services.market_data import get_data_timestamp
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)

_DUPLICATE_COOLDOWN_HOURS = 4


def _is_market_hours() -> bool:
    """Rough US market hours check in UTC (14:30–21:00)."""
    now = datetime.now(timezone.utc)
    return now.weekday() < 5 and 14 <= now.hour < 21


def _in_quiet_hours(user_settings: UserSettings) -> bool:
    hour = datetime.now(timezone.utc).hour
    start = user_settings.quiet_hours_start
    end = user_settings.quiet_hours_end
    if start > end:  # wraps midnight
        return hour >= start or hour < end
    return start <= hour < end


def _quota_remaining(user: User, session: Session) -> int:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = session.exec(
        select(ScanUsage).where(ScanUsage.user_id == user.id, ScanUsage.date == today)
    ).first()
    limit = settings.PRO_SCANS_PER_DAY if user.plan == "pro" else settings.FREE_SCANS_PER_DAY
    used = usage.scan_count if usage else 0
    return max(0, limit - used)


def _recently_alerted(user_id: str, ticker: str, session: Session) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=_DUPLICATE_COOLDOWN_HOURS)
    existing = session.exec(
        select(TradeAlert).where(
            TradeAlert.user_id == user_id,
            TradeAlert.ticker == ticker,
            TradeAlert.created_at >= cutoff,
        )
    ).first()
    return existing is not None


def _increment_usage(user_id: str, session: Session) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = session.exec(
        select(ScanUsage).where(ScanUsage.user_id == user_id, ScanUsage.date == today)
    ).first()
    if usage:
        usage.scan_count += 1
        usage.estimated_cost_usd += 0.002
    else:
        usage = ScanUsage(user_id=user_id, date=today, scan_count=1, estimated_cost_usd=0.002)
    session.add(usage)


def _data_is_stale(ticker: str) -> bool:
    ts = get_data_timestamp(ticker)
    if ts is None:
        return True
    return ts < (datetime.now(timezone.utc) - timedelta(days=3))


async def run_strategy_scan(strategy_id: str) -> None:
    """Full pipeline for a single strategy. Called by the scheduler."""
    with Session(engine) as session:
        strategy = session.get(Strategy, strategy_id)
        if not strategy or not strategy.enabled:
            return

        user = session.get(User, strategy.user_id)
        if not user:
            return

        user_settings = session.exec(
            select(UserSettings).where(UserSettings.user_id == user.id)
        ).first()

        # Market hours check (skip for pro users if desired — keep for MVP)
        if not _is_market_hours():
            logger.debug("Strategy %s: outside market hours, skipping.", strategy_id)
            return

        if user_settings and _in_quiet_hours(user_settings):
            logger.debug("Strategy %s: user quiet hours, skipping.", strategy_id)
            return

        if settings.is_private_test:
            allowed, reason = can_call_claude(user.id, session)
            if not allowed:
                logger.debug("Strategy %s: %s", strategy_id, reason)
                return
        elif _quota_remaining(user, session) <= 0:
            logger.debug("Strategy %s: daily quota exhausted.", strategy_id)
            return

        # Fetch balance
        try:
            user_balance = await trading212_service.fetch_balance()
        except Exception as exc:
            logger.warning("Strategy %s: T212 balance fetch failed: %s", strategy_id, exc)
            return

        max_trade_amount = round(user_balance * (settings.MAX_RISK_PCT / 100.0), 2)
        watchlist: list[str] = strategy.watchlist or []

        if not watchlist:
            return

        # Formula scan
        candidates = scan_watchlist(watchlist, min_score=strategy.min_signal_score)
        if not candidates:
            logger.info("Strategy %s: no candidates above threshold.", strategy_id)
            strategy.last_scanned_at = datetime.now(timezone.utc)
            session.add(strategy)
            session.commit()
            return

        # Deduplicate and validate — Invest only (STOCK/ETF)
        validated = []
        for c in candidates[:5]:
            if _recently_alerted(user.id, c.ticker, session):
                continue
            try:
                valid_instrument, instrument_type = await trading212_service.validate_invest_instrument(c.ticker)
            except Exception:
                continue
            if not valid_instrument or instrument_type not in ("STOCK", "ETF"):
                continue
            validated.append(c)
            if len(validated) == 3:
                break

        if not validated:
            logger.info("Strategy %s: no validated, non-duplicate candidates.", strategy_id)
            strategy.last_scanned_at = datetime.now(timezone.utc)
            session.add(strategy)
            session.commit()
            return

        # Claude analysis
        try:
            rec = await claude_service.analyse_candidates(
                validated, user_balance, max_trade_amount, mission=None
            )
            record_claude_call(user.id, session)
        except ValueError as exc:
            logger.warning("Strategy %s: Claude validation failed: %s", strategy_id, exc)
            return

        top = validated[0]
        formula_score = int(round(top.score))
        claude_confidence = rec.claude_confidence
        portfolio_fit_score = 50
        action_strength = calculate_buy_action_strength(
            formula_score, claude_confidence, portfolio_fit_score
        )

        action = "WATCH"
        safety_flags: list[str] = []
        trading212_review_enabled = False
        suggested_amount = min(max_trade_amount, round(max_trade_amount * 0.7, 2))

        stale = _data_is_stale(top.ticker)
        if stale:
            action = "DO_NOT_ACT"
            safety_flags.append("Data stale.")

        if action != "DO_NOT_ACT":
            if formula_score < 70:
                action = "WATCH"
                safety_flags.append("Formula score below 70.")
            elif claude_confidence < strategy.min_confidence:
                action = "WATCH"
                safety_flags.append(f"Claude confidence below {strategy.min_confidence}.")
            elif action_strength < 70:
                action = "WATCH"
                safety_flags.append("Action Strength below 70.")
            elif suggested_amount > max_trade_amount:
                action = "DO_NOT_ACT"
                safety_flags.append("Suggested amount exceeds configured max risk percent.")
            else:
                action = "BUY_REVIEW"
                trading212_review_enabled = True

        action_label = label_for_action_strength(action_strength)
        score_interpretation = interpretation_for_score(action_strength)
        alert_title = f"Potential Invest setup: {top.ticker}"
        alert_body = f"Action Strength {action_strength}/100 — review in app."
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=120)

        alert = TradeAlert(
            user_id=user.id,
            strategy_id=strategy.id,
            ticker=top.ticker,
            action=action,
            signal_score=top.score,
            confidence=claude_confidence,
            formula_score=formula_score,
            claude_confidence=claude_confidence,
            portfolio_fit_score=portfolio_fit_score,
            action_strength=action_strength,
            action_label=action_label,
            score_interpretation=score_interpretation,
            action_strength_disclaimer=ACTION_STRENGTH_DISCLAIMER,
            trading212_review_enabled=trading212_review_enabled,
            suggested_amount=suggested_amount,
            price_at_alert=top.current_price,
            alert_title=alert_title,
            alert_body=alert_body,
            rationale=rec.plain_english_summary,
            risk_note="Manual review required before any trade.",
            key_factors=rec.key_factors,
            blocking_risks=rec.risks + rec.contradiction_notes,
            expires_at=expires_at,
            executable=trading212_review_enabled,
            safety_flags=safety_flags,
        )
        session.add(alert)
        session.add(AlertOutcome(alert_id=alert.id))
        session.add(SignalPerformance(
            user_id=user.id,
            alert_id=alert.id,
            ticker=top.ticker,
            strategy=strategy_id,
            action=action,
            formula_score=formula_score,
            claude_confidence=claude_confidence,
            action_strength=action_strength,
            action_label=action_label,
            price_at_alert=top.current_price,
            suggested_amount=suggested_amount,
        ))
        if not settings.is_private_test:
            _increment_usage(user.id, session)
        strategy.last_scanned_at = datetime.now(timezone.utc)
        session.add(strategy)
        session.commit()
        session.refresh(alert)

        logger.info(
            "SCHEDULED SCAN | strategy=%s | ticker=%s | score=%d | claude_conf=%d | action_strength=%d | action=%s",
            strategy_id, top.ticker, formula_score, claude_confidence, action_strength, action,
        )

        # Push notification — only for review-enabled alerts
        if trading212_review_enabled and settings.ENABLE_PUSH_NOTIFICATIONS:
            alert_ok, _ = can_send_alert(user.id, session)
            if alert_ok:
                tokens = session.exec(
                    select(DeviceToken).where(DeviceToken.user_id == user.id)
                ).all()
                if tokens:
                    sent = send_to_user_devices(
                        [t.token for t in tokens],
                        title=alert_title,
                        body=alert_body,
                        alert_id=alert.id,
                        ticker=top.ticker,
                        action_strength=action_strength,
                    )
                    if sent:
                        alert.push_sent = True
                        session.add(alert)
                        record_alert_sent(user.id, session)
                        session.commit()
