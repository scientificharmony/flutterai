"""
ETF scan flow tests.

Verifies:
- ETF missions route to the ETF watchlist (not stock-only).
- Generic missions route to the mixed watchlist.
- ETF missions never select a stock candidate.
- A valid ETF candidate can produce alert_created / BUY_REVIEW.
- ETF no_action when all candidates fail T212 validation.
- ETF no_action when ETFs exist but none meet the threshold.
- Custom body.watchlist overrides automatic routing.
"""
from unittest.mock import call, patch

import pytest


def _headers(device: str = "etf-flow-device"):
    return {"device-id": device}


class _EtfCandidate:
    ticker = "VUSA"
    score = 82.0
    current_price = 50.0


class _StockCandidate:
    ticker = "META"
    score = 88.0
    current_price = 350.0


class _LowScoreEtfCandidate:
    ticker = "VWRP"
    score = 45.0
    current_price = 90.0


class _Rec:
    claude_confidence = 85
    key_factors = ["Broad market ETF with healthy trend."]
    risks = ["Market conditions can change."]
    contradiction_notes = []
    plain_english_summary = "VUSA is a broad-market ETF suitable for manual review."


# ── Watchlist routing ─────────────────────────────────────────────────────────

def test_etf_mission_routes_to_etf_watchlist(client):
    """ETF mission must call scan_watchlist with the ETF watchlist, not stock-only."""
    from routers.scan import _DEFAULT_ETF_WATCHLIST

    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.scan_watchlist", return_value=[]) as mock_scan:
        client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity"},
            headers=_headers("etf-routing"),
        )

    mock_scan.assert_called_once_with(_DEFAULT_ETF_WATCHLIST, min_score=0.0)


def test_lower_risk_mission_routes_to_etf_watchlist(client):
    """Lower-risk / safer mission should also route to the ETF watchlist."""
    from routers.scan import _DEFAULT_ETF_WATCHLIST

    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.scan_watchlist", return_value=[]) as mock_scan:
        client.post(
            "/scan",
            json={"mission": "Find something safe and conservative"},
            headers=_headers("safe-routing"),
        )

    mock_scan.assert_called_once_with(_DEFAULT_ETF_WATCHLIST, min_score=0.0)


def test_generic_mission_routes_to_mixed_watchlist(client):
    """Generic mission should scan the mixed watchlist (stocks + ETFs)."""
    from routers.scan import _DEFAULT_MIXED_WATCHLIST

    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.scan_watchlist", return_value=[]) as mock_scan:
        client.post(
            "/scan",
            json={"mission": "Find a strong technology opportunity"},
            headers=_headers("generic-routing"),
        )

    mock_scan.assert_called_once_with(_DEFAULT_MIXED_WATCHLIST, min_score=0.0)


def test_custom_watchlist_overrides_etf_routing(client):
    """body.watchlist always takes precedence over automatic routing."""
    custom = ["TSLA", "AAPL"]

    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.scan_watchlist", return_value=[]) as mock_scan:
        client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity", "watchlist": custom},
            headers=_headers("custom-override"),
        )

    mock_scan.assert_called_once_with(custom, min_score=0.0)


# ── Hard ETF filter ───────────────────────────────────────────────────────────

def test_explicit_etf_mission_never_selects_stock(client):
    """When all validated candidates are STOCK, an ETF mission must return no_action."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument",
               return_value=(True, "STOCK")), \
         patch("routers.scan.scan_watchlist", return_value=[_StockCandidate()]), \
         patch("routers.scan._data_is_stale", return_value=False):
        res = client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity"},
            headers=_headers("etf-no-stock"),
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_action"
    assert body.get("alert") is None
    assert any("etf" in f.lower() for f in body.get("safety_flags", []))


def test_explicit_etf_mission_no_valid_etfs_message(client):
    """When no ETF passes T212 validation, return the ETF-specific no-candidates message."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument",
               return_value=(False, "UNKNOWN")), \
         patch("routers.scan.scan_watchlist", return_value=[_EtfCandidate()]), \
         patch("routers.scan._data_is_stale", return_value=False):
        res = client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity"},
            headers=_headers("etf-all-invalid"),
        )

    body = res.json()
    assert body["status"] == "no_action"
    assert "etf" in body.get("message", "").lower()


# ── ETF actionable alert ──────────────────────────────────────────────────────

def test_etf_mission_creates_alert_when_etf_qualifies(client, db_engine):
    """A valid ETF candidate that passes all gates must produce alert_created / BUY_REVIEW."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument",
               return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_EtfCandidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity", "watchlist": ["VUSA"]},
            headers=_headers("etf-alert-ok"),
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "alert_created"
    assert body["alert"]["ticker"] == "VUSA"
    assert body["alert"]["action"] == "BUY_REVIEW"
    assert body["alert"]["trading212_review_enabled"] is True


# ── ETF threshold-failure no_action ──────────────────────────────────────────

def test_etf_mission_no_action_when_score_too_low(client):
    """ETF candidate that exists but scores below threshold returns ETF-specific no_action."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument",
               return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_LowScoreEtfCandidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity", "watchlist": ["VWRP"]},
            headers=_headers("etf-low-score"),
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_action"
    assert body.get("alert") is None
    # message should be ETF-specific, not the generic threshold message
    assert "etf" in body.get("message", "").lower()


# ── Stock scan still works ────────────────────────────────────────────────────

def test_stock_mission_can_select_stock_candidate(client, db_engine):
    """A generic stock mission must still work through the existing pipeline."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument",
               return_value=(True, "STOCK")), \
         patch("routers.scan.scan_watchlist", return_value=[_StockCandidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=type(
             "R", (), {
                 "claude_confidence": 85,
                 "key_factors": ["Strong trend."],
                 "risks": ["Market can change."],
                 "contradiction_notes": [],
                 "plain_english_summary": "META is a valid setup.",
             }
         )()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find a strong technology opportunity", "watchlist": ["META"]},
            headers=_headers("stock-still-works"),
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "alert_created"
    assert body["alert"]["ticker"] == "META"
