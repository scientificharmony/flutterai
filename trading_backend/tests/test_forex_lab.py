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
