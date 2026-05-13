def test_forex_summary_returns_mock_practice_signals(client):
    response = client.get("/forex/summary", headers={"device-id": "forex-device"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["connected"] is False
    assert body["demo_balance"] == 5000.0
    assert body["risk_amount"] == 25.0
    assert body["signals"]
    assert body["signals"][0]["practice_only"] is True


def test_forex_scan_accepts_timeframe_and_pairs(client):
    response = client.post(
        "/forex/scan",
        headers={"device-id": "forex-device"},
        json={"timeframe": "1h", "pairs": ["EUR/USD", "GBP/USD"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pairs"] == ["EUR/USD", "GBP/USD"]
    assert {signal["timeframe"] for signal in body["signals"]} == {"1h"}


def test_forex_summary_uses_ig_snapshot_when_configured(monkeypatch):
    import httpx
    from services import forex_service

    forex_service._ig_session = None
    forex_service._epic_cache.clear()
    monkeypatch.setattr(forex_service.settings, "forex_provider", "ig")
    monkeypatch.setattr(forex_service.settings, "ig_api_key", "test-key")
    monkeypatch.setattr(forex_service.settings, "ig_username", "test-user")
    monkeypatch.setattr(forex_service.settings, "ig_password", "test-password")
    monkeypatch.setattr(forex_service.settings, "ig_account_type", "DEMO")

    def response(status_code, *, headers=None, json=None):
        return httpx.Response(
            status_code,
            headers=headers,
            json=json,
            request=httpx.Request("GET", "https://demo-api.ig.com/gateway/deal/test"),
        )

    def fake_post(url, **kwargs):
        assert url.endswith("/session")
        assert kwargs["headers"]["X-IG-API-KEY"] == "test-key"
        return response(
            200,
            headers={"CST": "cst-token", "X-SECURITY-TOKEN": "security-token"},
            json={"currentAccountId": "ABC123"},
        )

    def fake_get(url, **kwargs):
        assert kwargs["headers"]["CST"] == "cst-token"
        assert kwargs["headers"]["X-SECURITY-TOKEN"] == "security-token"
        if url.endswith("/markets"):
            return response(
                200,
                json={
                    "markets": [
                        {
                            "epic": "CS.D.EURUSD.CFD.IP",
                            "instrumentName": "EUR/USD",
                            "instrumentType": "CURRENCIES",
                        }
                    ]
                },
            )
        assert url.endswith("/markets/CS.D.EURUSD.CFD.IP")
        return response(
            200,
            json={"snapshot": {"bid": 1.082, "offer": 1.083, "marketStatus": "TRADEABLE"}},
        )

    monkeypatch.setattr(forex_service.httpx, "post", fake_post)
    monkeypatch.setattr(forex_service.httpx, "get", fake_get)

    summary = forex_service.get_forex_summary(pairs=["EUR/USD"])

    assert summary.provider == "ig"
    assert summary.connected is True
    assert summary.account_type == "DEMO"
    assert summary.signals[0].entry == 1.0825
    assert "IG demo snapshot" in summary.signals[0].rationale
