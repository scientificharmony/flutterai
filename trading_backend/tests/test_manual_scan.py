from unittest.mock import patch

from sqlmodel import Session, select

from models.db_models import AlertOutcome, SignalPerformance, TradeAlert


def _headers():
    return {"device-id": "manual-scan-device-1"}


class _Candidate:
    ticker = "VUSA"
    score = 82.0
    current_price = 50.0


class _StockCandidate:
    ticker = "META"
    score = 85.0
    current_price = 350.0


class _Rec:
    claude_confidence = 85
    key_factors = ["Strong trend."]
    risks = ["Market conditions can change."]
    contradiction_notes = []
    plain_english_summary = "VUSA matches the manual review rules."


def test_manual_scan_creates_alert_and_tracking_rows(client, db_engine):
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find Trading 212 Invest stock or ETF setups.", "watchlist": ["VUSA"]},
            headers=_headers(),
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "alert_created"
    assert body["alert"] is not None
    assert body["alert"]["action_strength"] is not None
    assert body["alert"]["action_label"]
    assert body["alert"]["trading212_review_enabled"] is True

    alert_id = body["alert"]["id"]
    with Session(db_engine) as session:
        alert = session.get(TradeAlert, alert_id)
        performance = session.exec(
            select(SignalPerformance).where(SignalPerformance.alert_id == alert_id)
        ).first()
        outcome = session.exec(
            select(AlertOutcome).where(AlertOutcome.alert_id == alert_id)
        ).first()

    assert alert is not None
    assert performance is not None
    assert outcome is not None


def test_manual_scan_max_risk_uses_percentage_and_caps_suggested_amount(client, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_risk_pct", 10.0)

    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Keep Trading 212 review manual.", "watchlist": ["VUSA"]},
            headers={"device-id": "manual-scan-device-2"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["max_trade_amount"] == 100.0
    assert body["alert"]["suggested_amount"] <= 100.0


def test_manual_scan_never_returns_null(client):
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.scan_watchlist", return_value=[]):
        res = client.post(
            "/scan",
            json={"mission": "Find valid Invest opportunities.", "watchlist": ["VUSA"]},
            headers={"device-id": "manual-scan-device-3"},
        )

    assert res.status_code == 200
    assert res.json() is not None
    assert res.json()["status"] == "no_action"


def test_do_not_act_returns_no_action_and_zero_suggested_amount(client, db_engine):
    """DO_NOT_ACT (stale data) must not create a TradeAlert or return alert_created."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=True), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find Trading 212 Invest setups.", "watchlist": ["VUSA"]},
            headers={"device-id": "manual-scan-device-dna"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_action"
    assert body.get("alert") is None
    assert body.get("suggested_amount", 0.0) == 0.0
    assert "safety_flags" in body

    # Ensure no TradeAlert was persisted for this user
    with Session(db_engine) as session:
        alerts = session.exec(select(TradeAlert).where(TradeAlert.user_id == body["user_id"] if "user_id" in body else True)).all()
        # body has no user_id in response; instead count all and ensure no alert with ticker VUSA and action DO_NOT_ACT
        alerts = session.exec(select(TradeAlert).where(TradeAlert.action == "DO_NOT_ACT")).all()
        assert len(alerts) == 0


def test_watch_returns_no_action_and_zero_suggested_amount(client, db_engine):
    """Low formula score leading to WATCH must not create an actionable alert."""
    class _LowScoreCandidate:
        ticker = "VUSA"
        score = 60.0
        current_price = 50.0

    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_LowScoreCandidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find Trading 212 Invest setups.", "watchlist": ["VUSA"]},
            headers={"device-id": "manual-scan-device-watch"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_action"
    assert body.get("alert") is None

    with Session(db_engine) as session:
        alerts = session.exec(select(TradeAlert).where(TradeAlert.action == "WATCH")).all()
        assert len(alerts) == 0


def test_unknown_validation_returns_no_action_no_alert(client, db_engine):
    """UNKNOWN validation must return no_action and must not create a TradeAlert."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(False, "UNKNOWN")), \
         patch("routers.scan.scan_watchlist", return_value=[_Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=False):
        res = client.post(
            "/scan",
            json={"mission": "Find Trading 212 Invest setups.", "watchlist": ["VUSA"]},
            headers={"device-id": "manual-scan-device-unk"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_action"
    assert body.get("alert") is None
    assert any("validation failed" in f.lower() for f in body.get("safety_flags", []))

    with Session(db_engine) as session:
        alerts = session.exec(select(TradeAlert).where(TradeAlert.ticker == "VUSA", TradeAlert.action == "DO_NOT_ACT")).all()
        assert len(alerts) == 0


def test_explicit_etf_mission_excludes_stocks(client, db_engine):
    """When mission asks for an ETF, a stock must not be selected as top candidate."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", side_effect=lambda t: (True, "STOCK") if t == "META" else (False, "UNKNOWN")), \
         patch("routers.scan.scan_watchlist", return_value=[_StockCandidate(), _Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=False):
        res = client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity", "watchlist": ["META", "VUSA"]},
            headers={"device-id": "manual-scan-device-etf"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_action"
    assert body.get("alert") is None
    assert any("etf" in f.lower() for f in body.get("safety_flags", []))


def test_explicit_etf_mission_selects_etf_when_available(client, db_engine):
    """When mission asks for ETF and a valid ETF exists, it should be chosen."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=1000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", side_effect=lambda t: (True, "ETF") if t == "VUSA" else (True, "STOCK")), \
         patch("routers.scan.scan_watchlist", return_value=[_StockCandidate(), _Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find a safer ETF opportunity", "watchlist": ["META", "VUSA"]},
            headers={"device-id": "manual-scan-device-etf-ok"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "alert_created"
    assert body["alert"]["ticker"] == "VUSA"
    assert body["alert"]["action"] == "BUY_REVIEW"


def test_buy_review_returns_positive_suggested_amount_within_max(client):
    """BUY_REVIEW with executable=true should return suggested_amount > 0 and <= max_trade_amount."""
    with patch("routers.scan.trading212_service.fetch_balance", return_value=5000.0), \
         patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(True, "ETF")), \
         patch("routers.scan.scan_watchlist", return_value=[_Candidate()]), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()), \
         patch("routers.scan.can_call_claude", return_value=(True, "")), \
         patch("routers.scan.record_claude_call"):
        res = client.post(
            "/scan",
            json={"mission": "Find a strong setup.", "watchlist": ["VUSA"]},
            headers={"device-id": "manual-scan-device-suggest"},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "alert_created"
    assert body["alert"]["suggested_amount"] > 0
    assert body["alert"]["suggested_amount"] <= body["max_trade_amount"]
