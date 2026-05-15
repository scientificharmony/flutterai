from types import SimpleNamespace


def test_cfd_entry_scanner_creates_alert_and_respects_cooldown(db_engine, monkeypatch):
    import asyncio
    from sqlmodel import Session, select

    from config import settings
    from models.db_models import CfdEntryAlert, DeviceToken, User
    from workers import cfd_entry_scanner_job

    # Ensure the worker uses the in-memory test engine
    monkeypatch.setattr(cfd_entry_scanner_job, "engine", db_engine)

    # Enable pushes + cfd scanner in this test context
    monkeypatch.setattr(settings, "enable_push_notifications", True)
    monkeypatch.setattr(settings, "enable_cfd_entry_alerts", True)
    monkeypatch.setattr(settings, "cfd_min_signal_strength", 70)
    monkeypatch.setattr(settings, "cfd_entry_cooldown_hours", 4)

    sent = []

    def _send(tokens, **kwargs):
        sent.append((tokens, kwargs))
        return True

    monkeypatch.setattr(cfd_entry_scanner_job, "send_to_user_devices", _send)

    signal = SimpleNamespace(
        market="FTSE 100",
        epic="IX.D.FTSE.CFD.IP",
        direction="LONG",
        strength=82,
        timeframe="15m",
        entry=8000.0,
        stop_loss=7960.0,
        take_profit=8080.0,
        risk_amount=50.0,
        contract_size=1.0,
        rationale="Test rationale",
    )
    summary = SimpleNamespace(provider="ig", signals=[signal])
    monkeypatch.setattr(cfd_entry_scanner_job, "get_cfd_summary", lambda timeframe="15m", markets=None: summary)

    with Session(db_engine) as session:
        user = User(device_id="cfd-device", plan="pro")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(DeviceToken(user_id=user.id, token="tok1", platform="android"))
        session.commit()

    asyncio.run(cfd_entry_scanner_job.run_cfd_entry_scanner())
    asyncio.run(cfd_entry_scanner_job.run_cfd_entry_scanner())

    with Session(db_engine) as session:
        alerts = session.exec(select(CfdEntryAlert)).all()
        assert len(alerts) == 1
        assert alerts[0].push_sent is True
        assert alerts[0].market == "FTSE 100"
        assert alerts[0].direction == "LONG"

    assert len(sent) == 1
    assert sent[0][1]["notification_type"] == "cfd_entry_alert"
