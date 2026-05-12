"""
Pie Builder safety and freshness tests.

Scenarios
---------
1.  Stale data          — candidate rejected; response non-executable, no 422
2.  Invalid instrument  — T212 invest check fails; slice excluded; invest_only_verified=False
3.  Amount too low      — warning present; still returns 200
4.  No valid candidates — non-executable 200 with safety flag; no 422
5.  Valid low risk      — executable, ETF >= 90%, slices sum to 100%
6.  Valid medium risk   — executable, ETF >= 70%, slices sum to 100%
7.  Valid high risk     — executable, ETF >= 50%, slices sum to 100%
8.  Freshness metadata  — fields present; valid_until = market_data_timestamp + 24 h
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

from tests.conftest import make_candidate
import itertools

_device_counter = itertools.count(1)

_BASE = {
    "goal": "balanced_growth",
    "risk_level": "medium",
    "total_amount": 500.0,
    "time_horizon": "3 years",
    "preferred_themes": [],
    "excluded_themes": [],
}


def _post(client, overrides=None):
    # Unique device-id per call so quota never blocks tests
    headers = {"device-id": f"test-device-{next(_device_counter):04d}"}
    return client.post("/pie/build", json={**_BASE, **(overrides or {})}, headers=headers)


# ── Shared mock helpers ───────────────────────────────────────────────────────

def _patch_claude():
    async def _fake(slices, goal, risk_level, time_horizon, total_amount):
        return {
            "pie_name": "Test Portfolio",
            "overall_rationale": "Test rationale.",
            "slice_rationales": {s.candidate.ticker: "Good." for s in slices},
            "risk_note": "Risk exists.",
        }
    return patch("routers.pie.explain_pie", side_effect=_fake)


def _patch_t212_valid(instrument_type="ETF"):
    async def _validate(ticker):
        return True, instrument_type
    return patch(
        "routers.pie.trading212_service.validate_invest_instrument",
        side_effect=_validate,
    )


def _patch_t212_invalid():
    async def _validate(ticker):
        return False, "UNKNOWN"
    return patch(
        "routers.pie.trading212_service.validate_invest_instrument",
        side_effect=_validate,
    )


def _patch_t212_name():
    return patch(
        "routers.pie.trading212_service.get_instrument_name",
        side_effect=lambda t: t,
    )


def _patch_score_fresh(instrument_type="ETF"):
    """All tickers score well with today's data."""
    _counter = {"n": 0}

    def _score(ticker, theme, itype, already):
        _counter["n"] += 1
        return make_candidate(
            ticker=ticker,
            instrument_type=instrument_type,
            theme=theme,
            score=82.0 - _counter["n"],  # slight variation so ordering is deterministic
            newest_offset_days=0,
        )
    return patch("routers.pie.score_pie_candidate", side_effect=_score)


def _patch_score_stale(offset_days=10):
    """All tickers return data older than DATA_STALENESS_DAYS (3)."""
    def _score(ticker, theme, itype, already):
        return make_candidate(ticker=ticker, theme=theme, newest_offset_days=offset_days)
    return patch("routers.pie.score_pie_candidate", side_effect=_score)


def _patch_score_none():
    """score_pie_candidate always returns None (no data)."""
    return patch("routers.pie.score_pie_candidate", return_value=None)


# ── Test 1: Stale data ────────────────────────────────────────────────────────

def test_stale_data_rejected_and_non_executable(client):
    with _patch_t212_valid(), _patch_t212_name(), _patch_score_stale(), _patch_claude():
        r = _post(client)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executable"] is False
    assert d["slices"] == []
    assert any("stale" in f.lower() or "rejected" in f.lower() for f in d["safety_flags"]), d["safety_flags"]


# ── Test 2: Invalid instrument ────────────────────────────────────────────────

def test_invalid_instrument_excluded(client):
    with _patch_t212_invalid(), _patch_t212_name(), _patch_score_fresh(), _patch_claude():
        r = _post(client)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executable"] is False
    assert d["invest_only_verified"] is False
    assert d["slices"] == []


# ── Test 3: Amount too low ────────────────────────────────────────────────────

def test_amount_too_low_adds_warning(client):
    with _patch_t212_valid(), _patch_t212_name(), _patch_score_fresh(), _patch_claude():
        r = _post(client, {"total_amount": 2.0})

    assert r.status_code == 200, r.text
    d = r.json()
    assert any("low" in w.lower() or "minimum" in w.lower() for w in d["warnings"]), d["warnings"]


# ── Test 4: No valid candidates ───────────────────────────────────────────────

def test_no_valid_candidates_returns_200_non_executable(client):
    with _patch_t212_valid(), _patch_t212_name(), _patch_score_none(), _patch_claude():
        r = _post(client)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executable"] is False
    assert d["slices"] == []
    assert any("no candidates" in f.lower() for f in d["safety_flags"]), d["safety_flags"]


# ── Test 5: Valid low-risk Pie ────────────────────────────────────────────────

def test_valid_low_risk_pie(client):
    with _patch_t212_valid("ETF"), _patch_t212_name(), _patch_score_fresh("ETF"), _patch_claude():
        r = _post(client, {"goal": "safer_core", "risk_level": "low", "total_amount": 1000.0})

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executable"] is True
    assert d["manual_execution_only"] is True
    assert d["invest_only_verified"] is True

    slices = d["slices"]
    assert len(slices) >= 1

    total_pct = round(sum(s["allocation_percent"] for s in slices), 1)
    assert total_pct == 100.0, f"Slices sum to {total_pct}% not 100%"

    etf_pct = sum(s["allocation_percent"] for s in slices if s["instrument_type"] == "ETF")
    assert etf_pct >= 90.0, f"Low risk ETF% = {etf_pct}"

    for s in slices:
        assert s["allocation_percent"] >= 5.0


# ── Test 6: Valid medium-risk Pie ─────────────────────────────────────────────

def test_valid_medium_risk_pie(client):
    with _patch_t212_valid("ETF"), _patch_t212_name(), _patch_score_fresh("ETF"), _patch_claude():
        r = _post(client, {"goal": "balanced_growth", "risk_level": "medium", "total_amount": 500.0})

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executable"] is True

    slices = d["slices"]
    total_pct = round(sum(s["allocation_percent"] for s in slices), 1)
    assert total_pct == 100.0

    etf_pct = sum(s["allocation_percent"] for s in slices if s["instrument_type"] == "ETF")
    assert etf_pct >= 70.0, f"Medium risk ETF% = {etf_pct}"


# ── Test 7: Valid high-risk Pie ───────────────────────────────────────────────

def test_valid_high_risk_pie(client):
    with _patch_t212_valid("ETF"), _patch_t212_name(), _patch_score_fresh("ETF"), _patch_claude():
        r = _post(client, {"goal": "ai_technology", "risk_level": "high", "total_amount": 1000.0})

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["executable"] is True

    slices = d["slices"]
    total_pct = round(sum(s["allocation_percent"] for s in slices), 1)
    assert total_pct == 100.0

    etf_pct = sum(s["allocation_percent"] for s in slices if s["instrument_type"] == "ETF")
    assert etf_pct >= 50.0, f"High risk ETF% = {etf_pct}"


# ── Test 8: Freshness metadata ────────────────────────────────────────────────

def test_freshness_metadata_fields(client):
    with _patch_t212_valid("ETF"), _patch_t212_name(), _patch_score_fresh("ETF"), _patch_claude():
        r = _post(client, {"total_amount": 1000.0})

    assert r.status_code == 200, r.text
    d = r.json()

    assert d["manual_execution_only"] is True
    assert "data_freshness" in d
    assert d["data_freshness"]["status"] == "fresh"
    assert "market_data_timestamp" in d
    assert "valid_until" in d

    mdt = datetime.fromisoformat(d["market_data_timestamp"])
    vu  = datetime.fromisoformat(d["valid_until"])
    delta_seconds = abs((vu - mdt).total_seconds() - 86400)
    assert delta_seconds < 5, f"valid_until not ~24h after market_data_timestamp: delta={delta_seconds}s"
