def test_cfd_summary_returns_mock_practice_signals(client):
    response = client.get("/cfd/summary", headers={"device-id": "cfd-device"})

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["connected"] is False
    assert body["demo_balance"] == 5000.0
    assert "FTSE 100 Cash" in body["markets"]
    assert body["signals"]
    assert body["signals"][0]["practice_only"] is True


def test_cfd_scan_accepts_timeframe_and_markets(client):
    response = client.post(
        "/cfd/scan",
        headers={"device-id": "cfd-device"},
        json={"timeframe": "1h", "markets": ["FTSE 100 Cash", "Wall Street Cash"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["markets"] == ["FTSE 100 Cash", "Wall Street Cash"]
    assert {signal["timeframe"] for signal in body["signals"]} == {"1h"}


def test_cfd_summary_uses_ig_snapshot_when_configured(monkeypatch):
    from services import cfd_service

    monkeypatch.setattr(cfd_service.settings, "forex_provider", "ig")
    monkeypatch.setattr(cfd_service.settings, "ig_api_key", "test-key")
    monkeypatch.setattr(cfd_service.settings, "ig_username", "test-user")
    monkeypatch.setattr(cfd_service.settings, "ig_password", "test-password")
    monkeypatch.setattr(cfd_service.settings, "ig_account_type", "DEMO")
    monkeypatch.setattr(cfd_service, "_strength", lambda market, timeframe: 82)
    monkeypatch.setattr(cfd_service, "_direction", lambda market, strength: "LONG")
    monkeypatch.setattr(
        cfd_service,
        "_market_snapshots",
        lambda markets: [
            cfd_service.CfdMarketSnapshot(
                market="FTSE 100 Cash",
                price=10342.1,
                bid=10342.0,
                offer=10342.2,
                epic="IX.D.FTSE.CFD.IP",
                market_status="TRADEABLE",
                source="ig",
            )
        ],
    )

    summary = cfd_service.get_cfd_summary(markets=["FTSE 100 Cash"])

    assert summary.connected is True
    assert summary.signals[0].market == "FTSE 100 Cash"
    assert "IG demo CFD snapshot" in summary.signals[0].rationale
