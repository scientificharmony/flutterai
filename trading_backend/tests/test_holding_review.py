from unittest.mock import patch


def _headers():
    return {"device-id": "holding-review-device-1"}


def test_review_sell_fails_if_not_owned(client):
    res = client.post(
        "/scan/review-holding",
        json={"ticker": "AAPL", "currently_owned": False},
        headers=_headers(),
    )
    assert res.status_code == 200
    d = res.json()["alert"]
    assert d["action"] == "DO_NOT_ACT"
    assert d["trading212_review_enabled"] is False


def test_review_sell_succeeds_for_owned_weak_ticker(client):
    class _Rec:
        claude_confidence = 80
        key_factors = ["Weakness confirmed."]
        risks = ["Downtrend risk."]
        contradiction_notes = []
        plain_english_summary = "Holding shows sustained weakness."

    class _Cand:
        current_price = 100.0

    with patch("routers.scan.trading212_service.validate_invest_instrument", return_value=(True, "STOCK")), \
         patch("routers.scan._data_is_stale", return_value=False), \
         patch("routers.scan.calculate_weakness_score", return_value=85), \
         patch("routers.scan.calculate_drawdown_risk_score", return_value=80), \
         patch("routers.scan.calculate_exposure_risk_score", return_value=80), \
         patch("routers.scan.calculate_sell_action_strength", return_value=82), \
         patch("routers.scan.score_candidate", return_value=_Cand()), \
         patch("routers.scan.claude_service.analyse_candidates", return_value=_Rec()):
        res = client.post(
            "/scan/review-holding",
            json={
                "ticker": "AAPL",
                "currently_owned": True,
                "holding_loss_pct": 20,
                "holding_weight_pct": 15,
                "sector_concentration_pct": 40,
            },
            headers={"device-id": "holding-review-device-2"},
        )
    assert res.status_code == 200
    d = res.json()["alert"]
    assert d["action"] == "REVIEW_SELL"
    assert d["trading212_review_enabled"] is True
