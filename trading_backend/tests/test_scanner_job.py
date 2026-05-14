"""
Tests for the scheduled scanner job (workers/scanner_job.py).
Validates the modern Action Strength pipeline with correct percentage math,
Invest-only validation, and no obsolete Claude field access.

After tightening rules:
- Only actionable alerts (BUY_REVIEW / REVIEW_SELL with executable=true) are persisted.
- WATCH, DO_NOT_ACT, and validation-failed scans are logged but not stored as TradeAlert rows.
"""
import asyncio
from unittest.mock import patch, AsyncMock

import pytest
from sqlmodel import Session, select

from models.db_models import User, Strategy, TradeAlert, AlertOutcome, SignalPerformance
from models.schemas import ClaudeRecommendation
from services.formula_engine import ScoredCandidate
from workers.scanner_job import run_strategy_scan


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_candidate(ticker="AAPL", score=80.0, price=150.0):
    return ScoredCandidate(
        ticker=ticker,
        score=score,
        current_price=price,
        rsi=40.0,
        sma20=148.0,
        sma50=145.0,
        atr=3.0,
        volume_ratio=1.5,
        signal_summary="Good setup",
    )


def _make_claude_rec(ticker="AAPL", confidence=80):
    return ClaudeRecommendation(
        ticker=ticker,
        claude_confidence=confidence,
        reasoning_quality=75,
        key_factors=["Factor 1"],
        risks=["Risk 1"],
        contradiction_notes=[],
        plain_english_summary="Good candidate for manual review.",
    )


def _clean_scan_tables(db_engine):
    with Session(db_engine) as session:
        for model in (SignalPerformance, AlertOutcome, TradeAlert, Strategy, User):
            for row in session.exec(select(model)).all():
                session.delete(row)
        session.commit()


def _create_strategy(db_engine, watchlist=None, min_confidence=70, min_signal_score=75.0):
    with Session(db_engine) as session:
        user = User(device_id="scan-test-user", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)

        strategy = Strategy(
            user_id=user.id,
            name="Test Strategy",
            watchlist=watchlist or ["AAPL", "MSFT"],
            min_confidence=min_confidence,
            min_signal_score=min_signal_score,
            enabled=True,
            scan_interval_minutes=60,
        )
        session.add(strategy)
        session.commit()
        session.refresh(strategy)
        return strategy.id, user.id


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_risk_percentage_math(db_engine):
    """£1000 balance with MAX_RISK_PCT=10 → £100 max_trade → £70 suggested."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is not None
        assert alert.suggested_amount == 70.0  # min(100, 70)


def test_rejects_invalid_instrument(db_engine):
    """CFD/FOREX/CRYPTO must be skipped entirely."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(False, "CFD"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None


def test_rejects_non_invest_instrument_type(db_engine):
    """Even if valid_instrument=True, CRYPTO type must be rejected."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "CRYPTO"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None


def test_creates_trade_alert_with_action_strength_fields(db_engine):
    """Modern TradeAlert must include all Action Strength metadata."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is not None
        assert alert.ticker == "AAPL"
        assert alert.action == "BUY_REVIEW"
        assert alert.formula_score == 80
        assert alert.claude_confidence == 80
        assert alert.confidence == 80
        assert alert.portfolio_fit_score == 50
        assert alert.action_strength == 76  # (80*0.65)+(80*0.20)+(50*0.15)=75.5→76
        assert alert.action_label == "Strong Review"
        assert "Action Strength 76/100" in alert.score_interpretation
        assert "not a guarantee" in alert.action_strength_disclaimer
        assert alert.trading212_review_enabled is True
        assert alert.executable is True
        assert alert.alert_title == "AAPL looks like a good time to buy"
        assert alert.alert_body == "Tap to see why — takes 30 seconds to review."
        assert alert.risk_note == "Always review the chart yourself before buying. This app does not place trades."
        assert alert.key_factors == ["Factor 1"]
        assert alert.blocking_risks == ["Risk 1"]
        assert alert.safety_flags == []


def test_creates_alert_outcome(db_engine):
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is not None
        outcome = session.exec(select(AlertOutcome).where(AlertOutcome.alert_id == alert.id)).first()
        assert outcome is not None


def test_creates_signal_performance(db_engine):
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is not None
        perf = session.exec(select(SignalPerformance).where(SignalPerformance.alert_id == alert.id)).first()
        assert perf is not None
        assert perf.ticker == "AAPL"
        assert perf.formula_score == 80
        assert perf.claude_confidence == 80
        assert perf.action_strength == 76
        assert perf.action_label == "Strong Review"
        assert perf.price_at_alert == 150.0
        assert perf.suggested_amount == 70.0
        assert perf.strategy == strategy_id


def test_no_push_when_review_disabled(db_engine):
    """WATCH alerts must never trigger push notifications, and must NOT be persisted."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=60.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job.send_to_user_devices") as mock_push, \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None

    mock_push.assert_not_called()


def test_watch_when_formula_score_low(db_engine):
    """Low formula score → WATCH → no alert persisted."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=60.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None


def test_formula_score_below_claude_gate_skips_claude(db_engine):
    """Scheduled scans must not spend Claude calls on candidates that cannot pass formula gate."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine, min_signal_score=65.0)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=58.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))) as mock_claude, \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None

    mock_claude.assert_not_called()


def test_watch_when_claude_confidence_low(db_engine):
    """Claude confidence below strategy threshold → WATCH → no alert persisted."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine, min_confidence=75)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=70))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None


def test_watch_when_action_strength_low(db_engine):
    """formula=70, claude=70 → action_strength=67 < 70 → WATCH → no alert persisted."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=70.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=70))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None


def test_do_not_act_when_stale_data(db_engine):
    """Stale data → DO_NOT_ACT → no alert persisted."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=True), \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is None


def test_buy_review_when_all_thresholds_pass(db_engine):
    """All thresholds pass → BUY_REVIEW alert persisted with correct fields."""
    _clean_scan_tables(db_engine)
    strategy_id, user_id = _create_strategy(db_engine)

    with patch("workers.scanner_job.engine", db_engine):
        with patch("workers.scanner_job.trading212_service.fetch_balance", new=AsyncMock(return_value=1000.0)), \
             patch("workers.scanner_job.trading212_service.validate_invest_instrument", new=AsyncMock(return_value=(True, "STOCK"))), \
             patch("workers.scanner_job.scan_watchlist", return_value=[_make_candidate(score=80.0)]), \
             patch("workers.scanner_job.claude_service.analyse_candidates", new=AsyncMock(return_value=_make_claude_rec(confidence=80))), \
             patch("workers.scanner_job.can_call_claude", return_value=(True, "")), \
             patch("workers.scanner_job._data_is_stale", return_value=False), \
             patch("workers.scanner_job.can_send_alert", return_value=(True, "")), \
             patch("workers.scanner_job.send_to_user_devices", return_value=1) as mock_push, \
             patch("workers.scanner_job._is_market_hours", return_value=True), \
             patch("workers.scanner_job._in_quiet_hours", return_value=False):

            asyncio.run(run_strategy_scan(strategy_id))

    with Session(db_engine) as session:
        alert = session.exec(select(TradeAlert).where(TradeAlert.user_id == user_id)).first()
        assert alert is not None
        assert alert.action == "BUY_REVIEW"
        assert alert.trading212_review_enabled is True
        assert alert.executable is True

    # Push should NOT fire because ENABLE_PUSH_NOTIFICATIONS defaults to False
    mock_push.assert_not_called()
