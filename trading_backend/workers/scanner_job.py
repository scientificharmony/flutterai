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
from services.mission_filters import mission_requests_etf, mission_requests_lower_risk
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)

_DUPLICATE_COOLDOWN_HOURS = 4


def _is_market_hours() -> bool:
    """UK (LSE) 08:00–16:30 UTC or US (NYSE) 14:30–21:00 UTC, weekdays only."""
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    uk_open = 8 * 60        # 08:00 UTC
    uk_close = 16 * 60 + 30 # 16:30 UTC
    us_open = 14 * 60 + 30  # 14:30 UTC
    us_close = 21 * 60      # 21:00 UTC
    return (uk_open <= minutes < uk_close) or (us_open <= minutes < us_close)


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
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < (datetime.now(timezone.utc) - timedelta(days=3))


def _is_actionable(action: str, trading212_review_enabled: bool, executable: bool) -> bool:
    return action in ("BUY_REVIEW", "REVIEW_SELL") and trading212_review_enabled and executable


def _suggested_amount_for(action: str, executable: bool, max_trade_amount: float) -> float:
    if action != "BUY_REVIEW" or not executable:
        return 0.0
    return min(max_trade_amount, round(max_trade_amount * 0.7, 2))


def _candidate_log(candidates: list, limit: int = 5) -> str:
    return ", ".join(
        f"{c.ticker}:{int(round(c.score))}"
        for c in candidates[:limit]
    )


async def _pick_top_candidate(
    candidates: list,
    mission: str | None,
) -> tuple[object | None, list[object], list[str], str, dict[str, str]]:
    """
    Pick the best actionable candidate respecting mission constraints.
    Returns (candidate_or_None, validated_candidates, safety_flags, status_message, inst_type_map).
    """
    safety_flags: list[str] = []
    wants_etf = mission_requests_etf(mission)
    wants_lower_risk = mission_requests_lower_risk(mission)

    validated: list[dict] = []
    for c in candidates:
        try:
            valid, inst_type = await trading212_service.validate_invest_instrument(c.ticker)
        except Exception:
            continue
        if not valid:
            safety_flags.append(f"{c.ticker} validation failed: {inst_type}.")
            continue
        if inst_type not in ("STOCK", "ETF"):
            safety_flags.append(f"{c.ticker} rejected type: {inst_type}.")
            continue
        validated.append({"candidate": c, "type": inst_type})

    if not validated:
        return None, [], safety_flags, "No Trading 212 Invest validated candidates found.", {}

    if wants_etf:
        etf_only = [v for v in validated if v["type"] == "ETF"]
        if not etf_only:
            return None, [], safety_flags + ["Explicit ETF mission: no valid ETF candidates available."], "No valid ETF candidates for this mission.", {}
        validated = etf_only

    if wants_lower_risk and not wants_etf:
        validated.sort(key=lambda v: (0 if v["type"] == "ETF" else 1, -v["candidate"].score))
    else:
        validated.sort(key=lambda v: -v["candidate"].score)

    top = validated[0]["candidate"]
    validated_candidates = [v["candidate"] for v in validated]
    inst_type_map = {v["candidate"].ticker.upper(): v["type"] for v in validated}
    return top, validated_candidates, safety_flags, "", inst_type_map


async def run_strategy_scan(strategy_id: str) -> None:
    """Full pipeline for a single strategy. Called by the scheduler."""
    with Session(engine) as session:
        strategy = session.get(Strategy, strategy_id)
        if not strategy or not strategy.enabled:
            logger.info("Strategy %s: disabled or missing, skipping.", strategy_id)
            return

        user = session.get(User, strategy.user_id)
        if not user:
            logger.info("Strategy %s: user %s not found, skipping.", strategy_id, strategy.user_id)
            return

        user_settings = session.exec(
            select(UserSettings).where(UserSettings.user_id == user.id)
        ).first()

        # Market hours check (skip for pro users if desired — keep for MVP)
        if not _is_market_hours():
            logger.info("Strategy %s: outside market hours, skipping.", strategy_id)
            return

        if user_settings and _in_quiet_hours(user_settings):
            logger.info("Strategy %s: user quiet hours, skipping.", strategy_id)
            return

        if settings.is_private_test:
            allowed, reason = can_call_claude(user.id, session)
            if not allowed:
                logger.info("Strategy %s: %s", strategy_id, reason)
                return
        elif _quota_remaining(user, session) <= 0:
            logger.info("Strategy %s: daily quota exhausted.", strategy_id)
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
            logger.info("Strategy %s: empty watchlist, skipping.", strategy_id)
            return

        # Formula scan
        candidates = scan_watchlist(watchlist, min_score=strategy.min_signal_score)
        if not candidates:
            logger.info("Strategy %s: no candidates above threshold.", strategy_id)
            strategy.last_scanned_at = datetime.now(timezone.utc)
            session.add(strategy)
            session.commit()
            return
        logger.info(
            "Strategy %s: formula candidates | watchlist=%d | candidates=%d | top=%s",
            strategy_id,
            len(watchlist),
            len(candidates),
            _candidate_log(candidates),
        )

        # Deduplicate and validate — Invest only (STOCK/ETF)
        non_duplicate: list[object] = []
        for c in candidates[:5]:
            if _recently_alerted(user.id, c.ticker, session):
                logger.info("Strategy %s: %s skipped due to duplicate cooldown.", strategy_id, c.ticker)
                continue
            non_duplicate.append(c)

        top, validated_candidates, safety_flags, msg, inst_type_map = await _pick_top_candidate(non_duplicate, mission=None)
        if top is None:
            logger.info(
                "Strategy %s: %s | validation_flags=%s",
                strategy_id,
                msg,
                "; ".join(safety_flags) or "none",
            )
            strategy.last_scanned_at = datetime.now(timezone.utc)
            session.add(strategy)
            session.commit()
            return
        logger.info(
            "Strategy %s: validated candidates | top=%s | candidates=%s | types=%s | validation_flags=%s",
            strategy_id,
            top.ticker,
            _candidate_log(validated_candidates),
            inst_type_map,
            "; ".join(safety_flags) or "none",
        )

        formula_score = int(round(top.score))
        if formula_score < settings.SCHEDULED_MIN_FORMULA_SCORE_FOR_CLAUDE:
            logger.info(
                "SCHEDULED SCAN no-claude | strategy=%s | ticker=%s | formula_score=%d | reason=formula below %d",
                strategy_id,
                top.ticker,
                formula_score,
                settings.SCHEDULED_MIN_FORMULA_SCORE_FOR_CLAUDE,
            )
            strategy.last_scanned_at = datetime.now(timezone.utc)
            session.add(strategy)
            session.commit()
            return

        # Claude analysis
        try:
            claude_candidates = [top] + [
                c for c in validated_candidates if c.ticker != top.ticker
            ][: max(0, settings.CLAUDE_MAX_CANDIDATES - 1)]
            rec = await claude_service.analyse_candidates(
                claude_candidates,
                user_balance,
                max_trade_amount,
                mission=None,
                instrument_types=inst_type_map,
            )
            record_claude_call(user.id, session)
        except ValueError as exc:
            logger.warning("Strategy %s: Claude validation failed: %s", strategy_id, exc)
            return

        claude_confidence = rec.claude_confidence
        portfolio_fit_score = 70 if inst_type_map.get(top.ticker.upper()) == "ETF" else 50
        action_strength = calculate_buy_action_strength(
            formula_score, claude_confidence, portfolio_fit_score
        )

        action = "WATCH"
        trading212_review_enabled = False
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
            elif action_strength < settings.MIN_PUSH_ACTION_STRENGTH:
                action = "WATCH"
                safety_flags.append(f"Action Strength below {settings.MIN_PUSH_ACTION_STRENGTH}.")
            else:
                action = "BUY_REVIEW"
                trading212_review_enabled = True

        executable = trading212_review_enabled
        suggested_amount = _suggested_amount_for(action, executable, max_trade_amount)

        # Gate: only persist actionable alerts
        if not _is_actionable(action, trading212_review_enabled, executable):
            logger.info(
                "SCHEDULED SCAN no-action | strategy=%s | ticker=%s | formula_score=%d | claude_conf=%d | action_strength=%d | action=%s | flags=%s",
                strategy_id,
                top.ticker,
                formula_score,
                claude_confidence,
                action_strength,
                action,
                "; ".join(safety_flags) or "thresholds not met",
            )
            if not settings.is_private_test:
                _increment_usage(user.id, session)
            strategy.last_scanned_at = datetime.now(timezone.utc)
            session.add(strategy)
            session.commit()
            return

        # Actionable alert path
        action_label = label_for_action_strength(action_strength)
        score_interpretation = interpretation_for_score(action_strength)
        alert_title = f"{top.ticker} looks like a good time to buy"
        alert_body = f"Tap to see why — takes 30 seconds to review."
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
            what_is_this=rec.what_is_this,
            rationale=rec.plain_english_summary,
            risk_note="Always review the chart yourself before buying. This app does not place trades.",
            key_factors=rec.key_factors,
            blocking_risks=rec.risks + rec.contradiction_notes,
            expires_at=expires_at,
            executable=executable,
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
            "SCHEDULED SCAN alert_created | strategy=%s | ticker=%s | score=%d | claude_conf=%d | action_strength=%d | action=%s",
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
