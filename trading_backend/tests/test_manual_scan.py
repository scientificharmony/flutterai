from unittest.mock import patch

from sqlmodel import Session, select

from models.db_models import AlertOutcome, SignalPerformance, TradeAlert


def _headers():
    return {"device-id": "manual-scan-device-1"}


class _Candidate:
    ticker = "VUSA"
    score = 82.0
    current_price = 50.0


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
    assert res.json()["status"] == "no_signal"
