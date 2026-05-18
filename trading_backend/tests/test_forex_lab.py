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


def test_default_forex_universe_has_expanded_liquid_pairs():
    from services.forex_service import DEFAULT_FOREX_PAIRS

    assert len(DEFAULT_FOREX_PAIRS) == 8
    assert "EUR/USD" in DEFAULT_FOREX_PAIRS
    assert "USD/CAD" in DEFAULT_FOREX_PAIRS
    assert "NZD/USD" in DEFAULT_FOREX_PAIRS


def test_ig_snapshot_failure_skips_only_failed_pair(monkeypatch):
    from services import forex_service

    monkeypatch.setattr(forex_service.settings, "forex_provider", "ig")
    monkeypatch.setattr(forex_service, "provider_connected", lambda: True)
    monkeypatch.setattr(forex_service, "_get_ig_session", lambda: object())

    def fake_snapshot(pair, session):
        if pair == "GBP/CHF":
            raise RuntimeError("unsupported market")
        return forex_service.ForexMarketSnapshot(
            pair=pair,
            price=1.2345,
            bid=1.2344,
            offer=1.2346,
            epic=f"CS.D.{pair.replace('/', '')}.CFD.IP",
            market_status="TRADEABLE",
            source="ig",
        )

    monkeypatch.setattr(forex_service, "_ig_snapshot", fake_snapshot)

    snapshots = forex_service._market_snapshots(["EUR/USD", "GBP/CHF"])

    assert len(snapshots) == 1
    assert snapshots[0].pair == "EUR/USD"
    assert snapshots[0].source == "ig"
    assert snapshots[0].price == 1.2345


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
    monkeypatch.setattr(forex_service, "get_forex_ohlcv", lambda pair, **kwargs: None)

    summary = forex_service.get_forex_summary(pairs=["EUR/USD"])

    assert summary.provider == "ig"
    assert summary.connected is True
    assert summary.account_type == "DEMO"
    assert summary.signals[0].entry == 1.0825


def test_forex_position_can_be_opened_and_closed(client, monkeypatch):
    from routers import forex_positions

    monkeypatch.setattr(forex_positions, "get_forex_mid_price", lambda pair: 1.085)
    monkeypatch.setattr(forex_positions, "find_matching_ig_position", lambda pair, direction, exclude_deal_ids=None: None)

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
        lambda pair, direction, exclude_deal_ids=None: IgOpenPosition(
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


def test_forex_position_links_matching_ig_mini_market(client, monkeypatch):
    from services.forex_service import IgOpenPosition
    from routers import forex_positions

    monkeypatch.setattr(forex_positions, "get_forex_mid_price", lambda pair: 0.782)
    monkeypatch.setattr(
        forex_positions,
        "find_matching_ig_position",
        lambda pair, direction, exclude_deal_ids=None: IgOpenPosition(
            deal_id="DIMINIUSDCHF",
            epic="CS.D.USDCHF.MINI.IP",
            direction="BUY",
            size=0.5,
            instrument_name="USD/CHF Mini",
        ),
    )

    opened = client.post(
        "/forex/positions",
        headers={"device-id": "forex-mini-linked-device"},
        json={
            "pair": "USD/CHF",
            "direction": "LONG",
            "entry_price": 0.782,
            "stop_loss": 0.7785,
            "take_profit": 0.789,
            "risk_amount": 50,
            "position_units": 14285,
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
        lambda tokens, title, body, alert_id, ticker, action_strength=None, notification_type="trade_alert": sent.append((title, body, ticker)) or 1,
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


def test_forex_entry_scanner_sends_setup_push(db_engine, monkeypatch):
    from sqlmodel import Session
    from models.db_models import DeviceToken, ForexEntryAlert, User
    from services.forex_service import ForexSignalResponse, ForexSummaryResponse
    from workers import forex_entry_scanner_job

    sent = []

    signal = ForexSignalResponse(
        pair="EUR/USD",
        direction="SHORT",
        strength=82,
        timeframe="15m",
        entry=1.171,
        stop_loss=1.1745,
        take_profit=1.164,
        risk_reward=2.0,
        risk_amount=50,
        position_units=14285,
        rationale="Practice-only IG demo snapshot.",
        invalidation="Stop hit.",
    )
    summary = ForexSummaryResponse(
        provider="ig",
        connected=True,
        account_type="DEMO",
        demo_balance=10000,
        risk_bps=50,
        risk_amount=50,
        min_signal_strength=78,
        pairs=["EUR/USD"],
        signals=[signal],
    )

    monkeypatch.setattr(forex_entry_scanner_job.settings, "enable_forex_entry_alerts", True)
    monkeypatch.setattr(forex_entry_scanner_job.settings, "enable_push_notifications", True)
    monkeypatch.setattr(forex_entry_scanner_job, "engine", db_engine)
    monkeypatch.setattr(forex_entry_scanner_job, "get_forex_summary", lambda timeframe, pairs: summary)
    monkeypatch.setattr(
        forex_entry_scanner_job,
        "send_to_user_devices",
        lambda tokens, title, body, alert_id, ticker, action_strength=None, notification_type="trade_alert": sent.append((title, body, ticker, notification_type)) or 1,
    )

    with Session(db_engine) as session:
        user = User(device_id="forex-entry-failed-push-user", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(DeviceToken(user_id=user_id, token="existing-position-token", platform="android"))
        session.commit()

    import asyncio

    asyncio.run(forex_entry_scanner_job.run_forex_entry_scanner())

    with Session(db_engine) as session:
        alert = session.exec(
            select(ForexEntryAlert).where(ForexEntryAlert.user_id == user_id)
        ).first()
        assert alert is not None
        assert alert.pair == "EUR/USD"
        assert alert.push_sent is True

    assert sent
    assert "EUR/USD" in sent[0][0]
    assert sent[0][3] == "forex_entry_alert"

    sent.clear()
    asyncio.run(forex_entry_scanner_job.run_forex_entry_scanner())
    assert sent == []


def test_forex_entry_failed_push_does_not_start_cooldown(monkeypatch, db_engine):
    from datetime import datetime, timezone

    from sqlmodel import Session
    from models.db_models import ForexEntryAlert, User
    from workers import forex_entry_scanner_job

    monkeypatch.setattr(forex_entry_scanner_job.settings, "forex_entry_cooldown_hours", 2)
    monkeypatch.setattr(forex_entry_scanner_job, "engine", db_engine)

    with Session(db_engine) as session:
        user = User(device_id="forex-entry-user", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(
            ForexEntryAlert(
                user_id=user.id,
                pair="EUR/USD",
                direction="SHORT",
                strength=80,
                entry_price=1.171,
                stop_loss=1.1745,
                take_profit=1.164,
                risk_amount=50,
                position_units=14285,
                push_sent=False,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        assert forex_entry_scanner_job._recent_entry_alert(
            user.id,
            "EUR/USD",
            "SHORT",
            session,
        ) is False


def test_forex_entry_scanner_skips_existing_open_position(db_engine, monkeypatch):
    from sqlmodel import Session
    from models.db_models import DeviceToken, ForexPosition, ForexEntryAlert, User
    from services.forex_service import ForexSignalResponse, ForexSummaryResponse
    from workers import forex_entry_scanner_job

    sent = []

    signal = ForexSignalResponse(
        pair="EUR/USD",
        direction="SHORT",
        strength=82,
        timeframe="15m",
        entry=1.171,
        stop_loss=1.1745,
        take_profit=1.164,
        risk_reward=2.0,
        risk_amount=50,
        position_units=14285,
        rationale="Practice-only IG demo snapshot.",
        invalidation="Stop hit.",
    )
    summary = ForexSummaryResponse(
        provider="ig",
        connected=True,
        account_type="DEMO",
        demo_balance=10000,
        risk_bps=50,
        risk_amount=50,
        min_signal_strength=75,
        pairs=["EUR/USD"],
        signals=[signal],
    )

    monkeypatch.setattr(forex_entry_scanner_job.settings, "enable_forex_entry_alerts", True)
    monkeypatch.setattr(forex_entry_scanner_job.settings, "enable_push_notifications", True)
    monkeypatch.setattr(forex_entry_scanner_job, "engine", db_engine)
    monkeypatch.setattr(forex_entry_scanner_job, "get_forex_summary", lambda timeframe, pairs: summary)
    monkeypatch.setattr(
        forex_entry_scanner_job,
        "send_to_user_devices",
        lambda tokens, title, body, alert_id, ticker, action_strength=None, notification_type="trade_alert": sent.append((title, body, ticker)) or 1,
    )

    with Session(db_engine) as session:
        user = User(device_id="forex-existing-position-user", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(DeviceToken(user_id=user_id, token="entry-token", platform="android"))
        session.add(
            ForexPosition(
                user_id=user_id,
                pair="EUR/USD",
                direction="SHORT",
                entry_price=1.171,
                stop_loss=1.1745,
                take_profit=1.164,
                risk_amount=50,
                position_units=14285,
            )
        )
        session.commit()

    import asyncio

    asyncio.run(forex_entry_scanner_job.run_forex_entry_scanner())

    with Session(db_engine) as session:
        alert = session.exec(
            select(ForexEntryAlert).where(ForexEntryAlert.user_id == user_id)
        ).first()
        assert alert is None

    assert sent == []


def test_forex_entry_alerts_returns_recent_pushed_alerts(client, db_engine):
    from sqlmodel import Session, select

    from config import settings
    from models.db_models import ForexEntryAlert, ForexPosition, User

    client.get("/forex/summary", headers={"device-id": "forex-alert-history-user"})
    with Session(db_engine) as session:
        user = session.exec(select(User).where(User.device_id == settings.TEST_USER_ID)).first()
        assert user is not None
        session.add(
            ForexEntryAlert(
                user_id=user.id,
                pair="GBP/CHF",
                direction="SHORT",
                strength=82,
                entry_price=1.05595,
                stop_loss=1.05945,
                take_profit=1.04895,
                risk_amount=50,
                position_units=14285,
                rationale="Practice-only IG demo snapshot.",
                push_sent=True,
            )
        )
        session.add(
            ForexEntryAlert(
                user_id=user.id,
                pair="EUR/USD",
                direction="SHORT",
                strength=80,
                entry_price=1.1697,
                stop_loss=1.1732,
                take_profit=1.1627,
                risk_amount=50,
                position_units=14285,
                rationale="Practice-only IG demo snapshot.",
                push_sent=False,
            )
        )
        session.add(
            ForexPosition(
                user_id=user.id,
                pair="GBP/CHF",
                direction="SHORT",
                entry_price=1.05595,
                stop_loss=1.05945,
                take_profit=1.04895,
                risk_amount=50,
                position_units=14285,
                status="open",
            )
        )
        session.commit()

    response = client.get("/forex/entry-alerts", headers={"device-id": "forex-alert-history-user"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["pair"] == "GBP/CHF"
    assert body[0]["direction"] == "SHORT"
    assert body[0]["tracked"] is True


def test_execute_forex_entry_alert_places_ig_demo_trade(client, db_engine, monkeypatch):
    from sqlmodel import Session, select

    from config import settings
    from models.db_models import ForexEntryAlert, User
    from services.forex_service import IgPlacedPosition
    from routers import forex

    monkeypatch.setattr(forex.settings, "forex_provider", "ig")
    monkeypatch.setattr(forex.settings, "ig_account_type", "DEMO")
    monkeypatch.setattr(forex.settings, "forex_ig_size", 0.5)
    monkeypatch.setattr(forex.settings, "forex_execution_max_slippage_pips", 15)
    monkeypatch.setattr(forex, "get_forex_mid_price", lambda pair: 1.05596)
    placed = []
    monkeypatch.setattr(
        forex,
        "place_ig_demo_position",
        lambda pair, direction, size, stop_level, limit_level: placed.append((pair, direction, size, stop_level, limit_level))
        or IgPlacedPosition(
            deal_id="DIPLACED",
            deal_reference="REFPLACED",
            epic="CS.D.GBPCHF.CFD.IP",
            direction="SELL",
            size=size,
        ),
    )
    monkeypatch.setattr(forex, "find_matching_ig_position", lambda pair, direction: None)

    client.get("/forex/summary", headers={"device-id": "forex-execute-alert-user"})
    with Session(db_engine) as session:
        user = session.exec(select(User).where(User.device_id == settings.TEST_USER_ID)).first()
        assert user is not None
        alert = ForexEntryAlert(
            user_id=user.id,
            pair="NZD/USD",
            direction="SHORT",
            strength=82,
            entry_price=1.05595,
            stop_loss=1.05945,
            take_profit=1.04895,
            risk_amount=50,
            position_units=14285,
            rationale="Practice-only IG demo snapshot.",
            push_sent=True,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        alert_id = alert.id

    response = client.post(
        f"/forex/entry-alerts/{alert_id}/execute-demo",
        headers={"device-id": "forex-execute-alert-user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pair"] == "NZD/USD"
    assert body["direction"] == "SHORT"
    assert body["ig_linked"] is True
    assert placed == [("NZD/USD", "SHORT", 0.5, 1.05945, 1.04895)]


def _make_ohlcv_df(sma20_above_sma50: bool = True, rsi_val: float = 52.0, atr_val: float = 0.0008) -> "pd.DataFrame":
    """Build a minimal OHLCV DataFrame with predictable indicator values."""
    import numpy as np
    import pandas as pd

    n = 60
    # Create a trending close series so SMA20/SMA50 behave as requested
    if sma20_above_sma50:
        close = pd.Series([1.10 + i * 0.0005 for i in range(n)])
    else:
        close = pd.Series([1.10 - i * 0.0005 for i in range(n)])

    high = close + 0.0005
    low = close - 0.0005
    volume = pd.Series([1000.0] * n)

    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})
    return df


def test_real_signal_long_when_sma20_above_sma50(monkeypatch):
    from services import forex_service
    from services.market_data import OHLCVData
    from datetime import datetime, timezone

    df = _make_ohlcv_df(sma20_above_sma50=True)
    fake_data = OHLCVData(
        ticker="EUR/USD",
        df=df,
        current_price=float(df["Close"].iloc[-1]),
        current_volume=1000.0,
        data_timestamp=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(forex_service, "get_forex_ohlcv", lambda pair, **kwargs: fake_data)
    monkeypatch.setattr(forex_service.settings, "forex_min_signal_strength", 50)

    strength, direction = forex_service._real_signal("EUR/USD")

    assert direction == "LONG"
    assert strength >= 40


def test_real_signal_short_when_sma20_below_sma50(monkeypatch):
    from services import forex_service
    from services.market_data import OHLCVData
    from datetime import datetime, timezone

    df = _make_ohlcv_df(sma20_above_sma50=False)
    fake_data = OHLCVData(
        ticker="EUR/USD",
        df=df,
        current_price=float(df["Close"].iloc[-1]),
        current_volume=1000.0,
        data_timestamp=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(forex_service, "get_forex_ohlcv", lambda pair, **kwargs: fake_data)

    strength, direction = forex_service._real_signal("EUR/USD")

    assert direction in {"SHORT", "NO_TRADE"}


def test_real_signal_falls_back_when_no_data(monkeypatch):
    from services import forex_service

    monkeypatch.setattr(forex_service, "get_forex_ohlcv", lambda pair, **kwargs: None)

    strength, direction = forex_service._real_signal("EUR/USD")

    assert 0 <= strength <= 100
    assert direction in {"LONG", "SHORT", "NO_TRADE"}


def test_atr_stops_long_gives_correct_rr(monkeypatch):
    from services import forex_service
    from services.indicators import compute_all

    df = _make_ohlcv_df(sma20_above_sma50=True)
    df_ind = compute_all(df)
    price = float(df_ind["Close"].iloc[-1])

    stop_loss, take_profit = forex_service._atr_stops(df_ind, "LONG", price, "EUR/USD")

    assert stop_loss < price < take_profit
    rr = (take_profit - price) / (price - stop_loss)
    assert abs(rr - 2.0) < 0.01


def test_atr_stops_short_gives_correct_rr(monkeypatch):
    from services import forex_service
    from services.indicators import compute_all

    df = _make_ohlcv_df(sma20_above_sma50=False)
    df_ind = compute_all(df)
    price = float(df_ind["Close"].iloc[-1])

    stop_loss, take_profit = forex_service._atr_stops(df_ind, "SHORT", price, "GBP/USD")

    assert take_profit < price < stop_loss
    rr = (price - take_profit) / (stop_loss - price)
    assert abs(rr - 2.0) < 0.01


def test_build_signal_uses_real_indicators(monkeypatch):
    from services import forex_service
    from services.market_data import OHLCVData
    from datetime import datetime, timezone

    df = _make_ohlcv_df(sma20_above_sma50=True)
    fake_data = OHLCVData(
        ticker="EUR/USD",
        df=df,
        current_price=float(df["Close"].iloc[-1]),
        current_volume=1000.0,
        data_timestamp=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(forex_service, "get_forex_ohlcv", lambda pair, **kwargs: fake_data)
    monkeypatch.setattr(forex_service.settings, "forex_min_signal_strength", 50)

    snapshot = forex_service.ForexMarketSnapshot(
        pair="EUR/USD",
        price=1.125,
        bid=1.1249,
        offer=1.1251,
        epic="CS.D.EURUSD.CFD.IP",
        market_status="TRADEABLE",
        source="ig",
    )
    signal = forex_service.build_signal(snapshot, "15m")

    assert signal.pair == "EUR/USD"
    assert signal.direction in {"LONG", "SHORT", "NO_TRADE"}
    assert 0 <= signal.strength <= 100
    if signal.direction != "NO_TRADE":
        assert "SMA20" in signal.rationale or "Strength" in signal.rationale
        assert signal.stop_loss != signal.entry
        assert signal.take_profit != signal.entry


def test_pair_to_yf_ticker_format():
    from services.market_data import _pair_to_yf_ticker

    assert _pair_to_yf_ticker("EUR/USD") == "EURUSD=X"
    assert _pair_to_yf_ticker("GBP/JPY") == "GBPJPY=X"
    assert _pair_to_yf_ticker("USD/CHF") == "USDCHF=X"


def test_ig_snapshot_uses_short_cache(monkeypatch):
    from services import forex_service

    forex_service._snapshot_cache.clear()
    forex_service._epic_cache.clear()
    monkeypatch.setattr(forex_service, "_ig_base_url", lambda: "https://demo-api.ig.com/gateway/deal")
    monkeypatch.setattr(forex_service, "_ig_headers", lambda version="1", session=None: {})

    calls = []

    class FakeResponse:
        def __init__(self, data, status_code=200):
            self._data = data
            self.status_code = status_code

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append((url, params))
        if url.endswith("/markets"):
            return FakeResponse({"markets": [{"epic": "CS.D.EURUSD.CFD.IP", "instrumentName": "EUR/USD Mini"}]})
        return FakeResponse({"snapshot": {"bid": 1.1, "offer": 1.2, "marketStatus": "TRADEABLE"}})

    monkeypatch.setattr(forex_service.httpx, "get", fake_get)

    session = forex_service.IgSession(cst="cst", security_token="token", account_id="acct", expires_at=999999)
    first = forex_service._ig_snapshot("EUR/USD", session)
    second = forex_service._ig_snapshot("EUR/USD", session)

    assert first is not None
    assert second is first
    assert first.price == 1.15
    assert len(calls) == 2


def test_execute_forex_entry_alert_falls_back_to_open_position_when_confirm_missing(client, db_engine, monkeypatch):
    from sqlmodel import Session, select

    from config import settings
    from models.db_models import ForexEntryAlert, User
    from services.forex_service import IgOpenPosition, IgPlacedPosition
    from routers import forex

    monkeypatch.setattr(forex.settings, "forex_provider", "ig")
    monkeypatch.setattr(forex.settings, "ig_account_type", "DEMO")
    monkeypatch.setattr(forex.settings, "forex_ig_size", 0.5)
    monkeypatch.setattr(forex.settings, "forex_execution_max_slippage_pips", 15)
    monkeypatch.setattr(forex, "get_forex_mid_price", lambda pair: 1.05596)
    monkeypatch.setattr(
        forex,
        "place_ig_demo_position",
        lambda pair, direction, size, stop_level, limit_level: IgPlacedPosition(
            deal_id="",
            deal_reference="REFONLY",
            epic="CS.D.NZDUSD.CFD.IP",
            direction="SELL",
            size=size,
        ),
    )
    monkeypatch.setattr(
        forex,
        "find_matching_ig_position",
        lambda pair, direction: IgOpenPosition(
            deal_id="DIFALLBACK",
            epic="CS.D.NZDUSD.CFD.IP",
            direction="SELL",
            size=0.5,
            created_date="2026-05-14T00:00:00Z",
            instrument_name="NZD/USD Mini",
        ),
    )

    client.get("/forex/summary", headers={"device-id": "forex-execute-fallback-user"})
    with Session(db_engine) as session:
        user = session.exec(select(User).where(User.device_id == settings.TEST_USER_ID)).first()
        assert user is not None
        alert = ForexEntryAlert(
            user_id=user.id,
            pair="NZD/USD",
            direction="SHORT",
            strength=82,
            entry_price=1.05595,
            stop_loss=1.05945,
            take_profit=1.04895,
            risk_amount=50,
            position_units=14285,
            rationale="Practice-only IG demo snapshot.",
            push_sent=True,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        alert_id = alert.id

    response = client.post(
        f"/forex/entry-alerts/{alert_id}/execute-demo",
        headers={"device-id": "forex-execute-fallback-user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ig_linked"] is True


def test_execute_forex_entry_alert_custom_uses_body_size_and_levels(client, db_engine, monkeypatch):
    from sqlmodel import Session, select

    from config import settings
    from models.db_models import ForexEntryAlert, User
    from services.forex_service import IgPlacedPosition
    from routers import forex

    monkeypatch.setattr(forex.settings, "forex_provider", "ig")
    monkeypatch.setattr(forex.settings, "ig_account_type", "DEMO")
    monkeypatch.setattr(forex.settings, "forex_execution_max_slippage_pips", 15)
    monkeypatch.setattr(forex, "get_forex_mid_price", lambda pair: 1.05596)

    captured = {}

    def _place(pair, direction, size, stop_level, limit_level):
        captured.update(
            pair=pair,
            direction=direction,
            size=size,
            stop_level=stop_level,
            limit_level=limit_level,
        )
        return IgPlacedPosition(
            deal_id="DICUSTOM",
            deal_reference="REFCUSTOM",
            epic="CS.D.GBPCHF.CFD.IP",
            direction="SELL",
            size=size,
        )

    monkeypatch.setattr(forex, "place_ig_demo_position", _place)
    monkeypatch.setattr(forex, "find_matching_ig_position", lambda pair, direction: None)

    client.get("/forex/summary", headers={"device-id": "forex-execute-custom-user"})
    with Session(db_engine) as session:
        user = session.exec(select(User).where(User.device_id == settings.TEST_USER_ID)).first()
        assert user is not None
        alert = ForexEntryAlert(
            user_id=user.id,
            pair="TEST/PAIR",
            direction="SHORT",
            strength=82,
            entry_price=1.05595,
            stop_loss=1.05945,
            take_profit=1.04895,
            risk_amount=50,
            position_units=14285,
            rationale="Practice-only IG demo snapshot.",
            push_sent=True,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        alert_id = alert.id

    response = client.post(
        f"/forex/entry-alerts/{alert_id}/execute-demo-custom",
        headers={"device-id": "forex-execute-custom-user"},
        json={"size": 0.7, "stop_loss": 1.06, "take_profit": 1.049},
    )
    assert response.status_code == 200
    assert captured["size"] == 0.7
    assert captured["stop_level"] == 1.06
    assert captured["limit_level"] == 1.049


def test_positions_endpoint_syncs_missing_ig_positions(client, db_engine, monkeypatch):
    from config import settings
    from routers import forex_positions
    from services.forex_service import IgOpenPosition

    monkeypatch.setattr(forex_positions, "get_ig_open_positions", lambda: [
        IgOpenPosition(
            deal_id="DISYNC1",
            epic="CS.D.USDCHF.CFD.IP",
            direction="BUY",
            size=0.5,
            level=0.78321,
            stop_level=0.77862,
            limit_level=0.78912,
            instrument_name="USD/CHF Mini",
        )
    ])

    client.get("/forex/summary", headers={"device-id": "forex-sync-user"})
    response = client.get("/forex/positions", headers={"device-id": "forex-sync-user"})
    assert response.status_code == 200
    body = response.json()
    assert any(p.get("ig_linked") and p.get("ig_deal_id") == "DISYNC1" for p in body)
