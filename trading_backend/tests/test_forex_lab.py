from sqlmodel import select


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


def test_forex_position_can_be_opened_and_closed(client, monkeypatch):
    from routers import forex_positions

    monkeypatch.setattr(forex_positions, "get_forex_mid_price", lambda pair: 1.085)
    monkeypatch.setattr(forex_positions, "find_matching_ig_position", lambda pair, direction: None)

    opened = client.post(
        "/forex/positions",
        headers={"device-id": "forex-device"},
        json={
            "pair": "EUR/USD",
            "direction": "LONG",
            "entry_price": 1.08,
            "stop_loss": 1.077,
            "take_profit": 1.086,
            "risk_amount": 50,
            "position_units": 10000,
            "timeframe": "15m",
        },
    )

    assert opened.status_code == 200
    body = opened.json()
    assert body["status"] == "open"
    assert body["current_pnl"] == 50.0
    assert body["assistant_status"] == "PROTECT_PROFIT"

    listed = client.get("/forex/positions", headers={"device-id": "forex-device"})
    assert listed.status_code == 200
    assert listed.json()[0]["pair"] == "EUR/USD"

    closed = client.post(
        f"/forex/positions/{body['id']}/close",
        headers={"device-id": "forex-device"},
        json={"close_price": 1.086},
    )

    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["realised_pnl"] == 60.0
    assert closed.json()["assistant_status"] == "CLOSED"


def test_forex_position_links_matching_ig_deal(client, monkeypatch):
    from services.forex_service import IgOpenPosition
    from routers import forex_positions

    monkeypatch.setattr(forex_positions, "get_forex_mid_price", lambda pair: 1.085)
    monkeypatch.setattr(
        forex_positions,
        "find_matching_ig_position",
        lambda pair, direction: IgOpenPosition(
            deal_id="DIAAAABBB",
            epic="CS.D.EURUSD.CFD.IP",
            direction="SELL",
            size=1.0,
        ),
    )

    opened = client.post(
        "/forex/positions",
        headers={"device-id": "forex-linked-device"},
        json={
            "pair": "EUR/USD",
            "direction": "SHORT",
            "entry_price": 1.08,
            "stop_loss": 1.083,
            "take_profit": 1.074,
            "risk_amount": 50,
            "position_units": 10000,
            "timeframe": "15m",
        },
    )

    assert opened.status_code == 200
    assert opened.json()["ig_linked"] is True


def test_forex_monitor_notifies_when_status_changes(db_engine, monkeypatch):
    from sqlmodel import Session
    from models.db_models import DeviceToken, ForexPosition, User
    from workers import forex_position_monitor_job

    sent = []

    monkeypatch.setattr(forex_position_monitor_job.settings, "enable_push_notifications", True)
    monkeypatch.setattr(forex_position_monitor_job, "engine", db_engine)
    monkeypatch.setattr(forex_position_monitor_job, "get_forex_mid_price", lambda pair: 1.086)
    monkeypatch.setattr(
        forex_position_monitor_job,
        "send_to_user_devices",
        lambda tokens, title, body, alert_id, ticker, action_strength=None: sent.append((title, body, ticker)) or 1,
    )

    with Session(db_engine) as session:
        user = User(device_id="forex-monitor-user", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(DeviceToken(user_id=user_id, token="monitor-token", platform="android"))
        position = ForexPosition(
            user_id=user_id,
            pair="EUR/USD",
            direction="LONG",
            entry_price=1.08,
            stop_loss=1.077,
            take_profit=1.086,
            risk_amount=50,
            position_units=10000,
            timeframe="15m",
            last_assistant_status="HOLD",
        )
        session.add(position)
        session.commit()

    import asyncio

    asyncio.run(forex_position_monitor_job.run_forex_position_monitoring())

    with Session(db_engine) as session:
        position = session.exec(
            select(ForexPosition).where(ForexPosition.user_id == user_id)
        ).first()
        assert position.last_assistant_status == "TAKE_PROFIT"
        assert position.last_notified_status == "TAKE_PROFIT"

    assert sent
    assert "target reached" in sent[0][0].lower()


def test_forex_monitor_auto_closes_demo_position(db_engine, monkeypatch):
    from sqlmodel import Session
    from models.db_models import ForexPosition, User
    from workers import forex_position_monitor_job

    closed = []

    monkeypatch.setattr(forex_position_monitor_job.settings, "enable_forex_auto_close", True)
    monkeypatch.setattr(forex_position_monitor_job.settings, "ig_account_type", "DEMO")
    monkeypatch.setattr(forex_position_monitor_job.settings, "enable_push_notifications", False)
    monkeypatch.setattr(forex_position_monitor_job, "engine", db_engine)
    monkeypatch.setattr(forex_position_monitor_job, "get_forex_mid_price", lambda pair: 1.086)
    monkeypatch.setattr(
        forex_position_monitor_job,
        "close_ig_position",
        lambda deal_id, direction, size: closed.append((deal_id, direction, size)) or "REF123",
    )

    with Session(db_engine) as session:
        user = User(device_id="forex-autoclose-user", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        position = ForexPosition(
            user_id=user_id,
            pair="EUR/USD",
            direction="LONG",
            entry_price=1.08,
            stop_loss=1.077,
            take_profit=1.086,
            risk_amount=50,
            position_units=10000,
            timeframe="15m",
            ig_deal_id="DIAUTOCLOSE",
            ig_epic="CS.D.EURUSD.CFD.IP",
            ig_size=1.0,
            last_assistant_status="HOLD",
        )
        session.add(position)
        session.commit()

    import asyncio

    asyncio.run(forex_position_monitor_job.run_forex_position_monitoring())

    with Session(db_engine) as session:
        position = session.exec(
            select(ForexPosition).where(ForexPosition.user_id == user_id)
        ).first()
        assert position.status == "closed"
        assert position.realised_pnl == 60.0

    assert ("DIAUTOCLOSE", "LONG", 1.0) in closed
