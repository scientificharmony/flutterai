import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from auth import get_current_user
from config import settings
from database import get_session
from models.db_models import AlertOutcome, DeviceToken, ScanUsage, SignalPerformance, TradeAlert, User
from models.schemas import (
    HoldingReviewRequest,
    ManualScanRequest,
    ScanResponse,
    TradeAlertResponse,
    interpretation_for_score,
    label_for_action_strength,
    ACTION_STRENGTH_DISCLAIMER,
)
from services import claude_service, trading212_service
from services.trading212_service import get_t212_ticker
from services.action_strength_engine import calculate_buy_action_strength
from services.action_strength_engine import calculate_sell_action_strength
from services.budget_service import can_call_claude, can_send_alert, record_alert_sent, record_claude_call
from services.formula_engine import scan_watchlist
from services.formula_engine import score_candidate
from services.holding_review_engine import (
    calculate_drawdown_risk_score,
    calculate_exposure_risk_score,
    calculate_weakness_score,
)
from services.market_data import get_data_timestamp
from services.mission_filters import mission_requests_etf, mission_requests_lower_risk
from services.notification_service import send_to_user_devices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scan", tags=["scan"])

_DEFAULT_STOCK_WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ"]

_DEFAULT_ETF_WATCHLIST = ["VUSAL", "VUAG", "VWRP", "VHYLL", "IITU", "EQQQL", "INRGL", "SWDA", "CSP1", "CNDX"]

_DEFAULT_MIXED_WATCHLIST = _DEFAULT_STOCK_WATCHLIST + _DEFAULT_ETF_WATCHLIST

# ── Quota helpers ───────────────────────────────────────────────────────────────

def _check_quota(user: User, session: Session) -> None:
    if settings.is_private_test:
        allowed, reason = can_call_claude(user.id, session)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = session.exec(select(ScanUsage).where(ScanUsage.user_id == user.id, ScanUsage.date == today)).first()
    limit = settings.PRO_SCANS_PER_DAY if user.plan == "pro" else settings.FREE_SCANS_PER_DAY
    if usage and usage.scan_count >= limit:
        raise HTTPException(status_code=429, detail="Daily AI budget reached. Claude scans are paused today to control API costs. Formula-only checks can still run.")


def _increment_usage(user: User, session: Session, cost_usd: float = 0.002) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    usage = session.exec(select(ScanUsage).where(ScanUsage.user_id == user.id, ScanUsage.date == today)).first()
    if usage:
        usage.scan_count += 1
        usage.estimated_cost_usd += cost_usd
    else:
        usage = ScanUsage(user_id=user.id, date=today, scan_count=1, estimated_cost_usd=cost_usd)
    session.add(usage)
    session.commit()


def _data_is_stale(ticker: str) -> bool:
    ts = get_data_timestamp(ticker)
    if ts is None:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < (datetime.now(timezone.utc) - timedelta(days=3))


# ── Scan helpers ──────────────────────────────────────────────────────────────

def _resolve_scan_no_action(
    user_balance: float,
    max_trade_amount: float,
    message: str,
    safety_flags: list[str],
) -> ScanResponse:
    return ScanResponse(
        status="no_action",
        user_balance=user_balance,
        max_trade_amount=max_trade_amount,
        message=message,
        safety_flags=safety_flags,
    )


def _is_actionable(action: str, trading212_review_enabled: bool, executable: bool) -> bool:
    return action in ("BUY_REVIEW", "REVIEW_SELL") and trading212_review_enabled and executable


def _suggested_amount_for(action: str, executable: bool, max_trade_amount: float) -> float:
    if action != "BUY_REVIEW" or not executable:
        return 0.0
    return min(max_trade_amount, round(max_trade_amount * 0.7, 2))


async def _pick_top_candidate(
    candidates: list,
    mission: Optional[str],
    user_balance: float,
    max_trade_amount: float,
) -> tuple[Optional[object], list[object], list[str], str, dict[str, str]]:
    """
    Pick the best actionable candidate respecting mission constraints.
    Returns (candidate_or_None, validated_candidates, safety_flags, status_message, inst_type_map).
    inst_type_map maps ticker -> "ETF" | "STOCK" for all validated candidates.
    """
    safety_flags: list[str] = []
    wants_etf = mission_requests_etf(mission)
    wants_lower_risk = mission_requests_lower_risk(mission)

    # Validate and annotate each candidate
    validated: list[dict] = []
    for c in candidates:
        valid, inst_type = await trading212_service.validate_invest_instrument(c.ticker)
        if not valid:
            safety_flags.append(f"{c.ticker} validation failed: {inst_type}.")
            continue
        if inst_type not in ("STOCK", "ETF"):
            safety_flags.append(f"{c.ticker} rejected type: {inst_type}.")
            continue
        validated.append({"candidate": c, "type": inst_type})

    inst_type_map: dict[str, str] = {v["candidate"].ticker: v["type"] for v in validated}

    if not validated:
        msg = (
            "No Trading 212 Invest ETF candidates were available for this mission."
            if wants_etf
            else "No Trading 212 Invest validated candidates found."
        )
        return None, [], safety_flags, msg, {}

    # Explicit ETF mission: hard exclude stocks
    if wants_etf:
        etf_only = [v for v in validated if v["type"] == "ETF"]
        if not etf_only:
            return (
                None, [],
                safety_flags + ["Explicit ETF mission: no valid ETF candidates available."],
                "No Trading 212 Invest ETF candidates were available for this mission.",
                inst_type_map,
            )
        validated = etf_only

    # Lower-risk mission: sort ETFs above stocks if both present
    if wants_lower_risk and not wants_etf:
        validated.sort(key=lambda v: (0 if v["type"] == "ETF" else 1, -v["candidate"].score))
    else:
        # Default: highest score first
        validated.sort(key=lambda v: -v["candidate"].score)

    top = validated[0]["candidate"]
    validated_candidates = [v["candidate"] for v in validated]
    return top, validated_candidates, safety_flags, "", inst_type_map


# ── Manual scan ─────────────────────────────────────────────────────────────────

@router.post("", response_model=ScanResponse)
async def manual_scan(
    body: ManualScanRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    _check_quota(user, session)

    try:
        user_balance = await trading212_service.fetch_balance()
    except Exception as exc:
        logger.error("T212 balance fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Unable to verify account balance. Scan blocked for safety.")

    max_trade_amount = round(user_balance * (settings.MAX_RISK_PCT / 100.0), 2)
    is_etf_mission = mission_requests_etf(body.mission)
    is_lower_risk_mission = mission_requests_lower_risk(body.mission)

    if body.watchlist:
        watchlist = body.watchlist
    elif is_etf_mission or is_lower_risk_mission:
        watchlist = _DEFAULT_ETF_WATCHLIST
    else:
        watchlist = _DEFAULT_MIXED_WATCHLIST

    # Phase 4: mission-aware candidate filtering
    candidates = scan_watchlist(watchlist, min_score=0.0)
    if not candidates:
        _increment_usage(user, session, cost_usd=0.0)
        no_candidates_msg = (
            "ETF candidates were reviewed, but none met the current signal threshold."
            if is_etf_mission
            else "No candidates available."
        )
        return _resolve_scan_no_action(
            user_balance, max_trade_amount,
            no_candidates_msg, ["No watchlist candidates scored above threshold."],
        )

    top, validated_candidates, safety_flags, msg, inst_type_map = await _pick_top_candidate(
        candidates, body.mission, user_balance, max_trade_amount
    )
    if top is None:
        _increment_usage(user, session, cost_usd=0.0)
        return _resolve_scan_no_action(user_balance, max_trade_amount, msg, safety_flags)

    formula_score = int(round(top.score))
    action = "WATCH"
    trading212_review_enabled = False
    # ETFs are inherently diversified — portfolio fit is higher by nature.
    portfolio_fit_score = 70 if inst_type_map.get(top.ticker) == "ETF" else 50
    # ETF action thresholds are slightly lower: stable instruments don't spike
    # in formula score the way individual stocks do.
    score_threshold = 65 if is_etf_mission else 70
    stale = _data_is_stale(top.ticker)

    if stale:
        action = "DO_NOT_ACT"
        safety_flags.append("Data stale.")

    allowed, budget_reason = can_call_claude(user.id, session)
    if not allowed:
        return ScanResponse(status="budget_reached", user_balance=user_balance, max_trade_amount=max_trade_amount, message=budget_reason, budget_reached=True)

    claude_candidates = [top] + [c for c in validated_candidates if c.ticker != top.ticker][:2]
    rec = await claude_service.analyse_candidates(
        claude_candidates, user_balance, max_trade_amount,
        mission=body.mission, instrument_types=inst_type_map,
    )
    record_claude_call(user.id, session)
    claude_confidence = rec.claude_confidence
    action_strength = calculate_buy_action_strength(formula_score, claude_confidence, portfolio_fit_score)

    if action != "DO_NOT_ACT":
        if formula_score < score_threshold:
            action = "WATCH"
            safety_flags.append(f"Formula score below {score_threshold}.")
        elif claude_confidence < 65:
            action = "WATCH"
            safety_flags.append("Claude confidence below 65.")
        elif action_strength < score_threshold:
            action = "WATCH"
            safety_flags.append(f"Action Strength below {score_threshold}.")
        else:
            action = "BUY_REVIEW"
            trading212_review_enabled = True

    executable = trading212_review_enabled
    suggested_amount = _suggested_amount_for(action, executable, max_trade_amount)

    # Phase 2 gate: only create alerts for actionable outcomes
    if not _is_actionable(action, trading212_review_enabled, executable):
        _increment_usage(user, session, cost_usd=0.0)
        if action == "DO_NOT_ACT":
            message = "Scan completed, but data was stale — no recommendation created."
        elif is_etf_mission:
            message = "ETF candidates were reviewed, but none met the current manual-review threshold."
        else:
            message = "Scan completed, but setup did not reach actionable review threshold."
        return _resolve_scan_no_action(
            user_balance, max_trade_amount, message, safety_flags,
        )

    # Actionable alert path
    action_label = label_for_action_strength(action_strength)
    score_interpretation = interpretation_for_score(action_strength)
    alert_title = f"{top.ticker} looks like a good time to buy"
    alert_body = "Tap to see why — takes 30 seconds to review."
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=120)

    alert = TradeAlert(
        user_id=user.id,
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
    session.add(
        SignalPerformance(
            user_id=user.id,
            alert_id=alert.id,
            ticker=top.ticker,
            action=action,
            formula_score=formula_score,
            claude_confidence=claude_confidence,
            action_strength=action_strength,
            action_label=action_label,
            price_at_alert=top.current_price,
            suggested_amount=suggested_amount,
        )
    )
    session.commit()
    session.refresh(alert)

    if trading212_review_enabled and settings.ENABLE_PUSH_NOTIFICATIONS:
        alert_ok, _ = can_send_alert(user.id, session)
        if alert_ok:
            tokens = session.exec(select(DeviceToken).where(DeviceToken.user_id == user.id)).all()
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

    if not settings.is_private_test:
        _increment_usage(user, session)

    _t212_ticker = get_t212_ticker(alert.ticker)
    return ScanResponse(
        status="alert_created",
        user_balance=user_balance,
        max_trade_amount=max_trade_amount,
        alert=TradeAlertResponse(
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
            t212_ticker=_t212_ticker,
            t212_review_url=f"https://www.trading212.com/trading-instruments/invest/{_t212_ticker}" if _t212_ticker else None,
            what_is_this=alert.what_is_this,
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
        ),
    )


# ── Push test ───────────────────────────────────────────────────────────────────

@router.post("/test-push")
async def test_push(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Send a test push notification to all registered devices for this user."""
    tokens = session.exec(select(DeviceToken).where(DeviceToken.user_id == user.id)).all()
    if not tokens:
        raise HTTPException(status_code=404, detail="No device tokens registered for this user.")
    sent = send_to_user_devices(
        [t.token for t in tokens],
        title="Hey Jimmy — test notification",
        body="Push pipeline confirmed working.",
        alert_id="test-push",
        ticker="TEST",
        action_strength=None,
    )
    return {"tokens_found": len(tokens), "sent": sent}


# ── Holding review ──────────────────────────────────────────────────────────────

@router.post("/review-holding", response_model=ScanResponse)
async def review_holding(
    body: HoldingReviewRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ticker = body.ticker.upper()
    if not body.currently_owned:
        return _resolve_scan_no_action(
            0.0, 0.0,
            "Ticker is not currently owned.",
            ["Not owned: review disabled."],
        )

    valid, inst_type = await trading212_service.validate_invest_instrument(ticker)
    stale = _data_is_stale(ticker)
    weakness_score = calculate_weakness_score(ticker) or 0
    drawdown_risk_score = calculate_drawdown_risk_score(body.holding_loss_pct)
    exposure_risk_score = calculate_exposure_risk_score(body.holding_weight_pct, body.sector_concentration_pct)

    candidate = score_candidate(ticker)
    claude_confidence = 50
    key_factors = ["Holding review generated from deterministic rules."]
    risks = ["Market conditions can change."]
    summary = "Holding may require manual sell/trim review."
    if candidate:
        rec = await claude_service.analyse_candidates([candidate], 0.0, 0.0, mission=body.mission)
        claude_confidence = rec.claude_confidence
        key_factors = rec.key_factors
        risks = rec.risks + rec.contradiction_notes
        summary = rec.plain_english_summary

    action_strength = calculate_sell_action_strength(
        weakness_score=weakness_score,
        drawdown_risk_score=drawdown_risk_score,
        claude_confidence=claude_confidence,
        exposure_risk_score=exposure_risk_score,
    )
    action = "HOLD"
    flags: list[str] = []
    if stale:
        action = "DO_NOT_ACT"
        flags.append("Data stale.")
    elif not valid:
        action = "DO_NOT_ACT"
        flags.append(f"Instrument validation failed: {inst_type}.")
    elif weakness_score < 70:
        flags.append("Weakness score below 70.")
    elif claude_confidence < 65:
        flags.append("Claude confidence below 65.")
    elif action_strength < 70:
        flags.append("Action Strength below 70.")
    else:
        action = "REVIEW_SELL"

    review_enabled = action == "REVIEW_SELL"
    label = label_for_action_strength(action_strength)
    interpretation = interpretation_for_score(action_strength)

    # Holding reviews always create an alert record for diagnostics,
    # but suggested_amount stays 0.0 unless it's an actionable sell review.
    suggested_amount = 0.0

    alert = TradeAlert(
        user_id=user.id,
        ticker=ticker,
        action=action,
        signal_score=float(weakness_score),
        confidence=claude_confidence,
        formula_score=0,
        claude_confidence=claude_confidence,
        weakness_score=weakness_score,
        drawdown_risk_score=drawdown_risk_score,
        exposure_risk_score=exposure_risk_score,
        action_strength=action_strength,
        action_label=label,
        score_interpretation=interpretation,
        action_strength_disclaimer=ACTION_STRENGTH_DISCLAIMER,
        trading212_review_enabled=review_enabled,
        suggested_amount=suggested_amount,
        price_at_alert=float(candidate.current_price) if candidate else 0.0,
        alert_title=f"Holding review: {ticker}",
        alert_body=f"Action Strength {action_strength}/100 — review manually.",
        rationale=summary,
        risk_note="Manual review required before any sell/trim action.",
        key_factors=key_factors,
        blocking_risks=risks,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=240),
        executable=review_enabled,
        safety_flags=flags,
    )
    session.add(alert)
    session.add(AlertOutcome(alert_id=alert.id))
    session.add(
        SignalPerformance(
            user_id=user.id,
            alert_id=alert.id,
            ticker=ticker,
            action=action,
            formula_score=0,
            claude_confidence=claude_confidence,
            action_strength=action_strength,
            action_label=label,
            price_at_alert=alert.price_at_alert,
            suggested_amount=suggested_amount,
        )
    )
    session.commit()
    session.refresh(alert)

    return ScanResponse(
        status="alert_created" if review_enabled else "no_action",
        user_balance=0.0,
        max_trade_amount=0.0,
        alert=TradeAlertResponse(
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
        ),
    )
