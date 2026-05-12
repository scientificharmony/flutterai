from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from config import settings
from database import get_session
from models.db_models import SignalPerformance, TradeAlert, User
from routers import admin
from services import notification_service


@pytest.fixture(autouse=True)
def reset_settings():
    original_mode = settings.app_mode
    original_admin_enabled = settings.enable_admin_routes
    original_admin_token = settings.admin_api_token
    original_push_enabled = settings.enable_push_notifications
    original_firebase_path = settings.firebase_service_account_path
    yield
    settings.app_mode = original_mode
    settings.enable_admin_routes = original_admin_enabled
    settings.admin_api_token = original_admin_token
    settings.enable_push_notifications = original_push_enabled
    settings.firebase_service_account_path = original_firebase_path
    notification_service._firebase_app = None


def _make_alert(user_id: str, ticker: str = "VUSA") -> TradeAlert:
    return TradeAlert(
        user_id=user_id,
        ticker=ticker,
        action="BUY_REVIEW",
        signal_score=80,
        confidence=75,
        formula_score=80,
        claude_confidence=75,
        action_strength=72,
        action_label="Strong Review",
        score_interpretation="Action Strength 72/100: Strong Review.",
        action_strength_disclaimer="Action Strength ranks how strongly this setup matches your rules.",
        trading212_review_enabled=True,
        suggested_amount=10,
        price_at_alert=100,
        alert_title="Review VUSA",
        alert_body="Manual review only.",
        rationale="Test alert.",
        risk_note="Test risk.",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def _override_session(db_engine):
    def _override():
        with Session(db_engine) as session:
            yield session

    return _override


def test_admin_endpoint_not_registered_when_disabled(client):
    settings.enable_admin_routes = False

    response = client.get("/admin/strategy-performance")

    assert response.status_code == 404


def test_admin_guard_requires_token_when_enabled(db_engine):
    settings.enable_admin_routes = True
    settings.admin_api_token = "secret-admin-token"
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[get_session] = _override_session(db_engine)

    with TestClient(app) as client:
        response = client.get("/admin/strategy-performance")

    assert response.status_code == 403


def test_admin_guard_accepts_correct_token(db_engine):
    settings.enable_admin_routes = True
    settings.admin_api_token = "secret-admin-token"
    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[get_session] = _override_session(db_engine)

    with TestClient(app) as client:
        response = client.get(
            "/admin/strategy-performance",
            headers={"x-admin-token": "secret-admin-token"},
        )

    assert response.status_code == 200


def test_private_mode_allows_missing_device_id(client):
    settings.app_mode = "private_test"

    response = client.get("/alerts")

    assert response.status_code == 200


def test_public_mode_requires_device_id(client):
    settings.app_mode = "public"

    response = client.get("/alerts")

    assert response.status_code == 401
    assert response.json()["detail"] == "device-id header is required."


def test_public_mode_accepts_device_id(client):
    settings.app_mode = "public"

    response = client.get("/alerts", headers={"device-id": "phone-1"})

    assert response.status_code == 200


def test_get_outcome_cannot_read_another_users_record(client, db_engine):
    settings.app_mode = "public"
    with Session(db_engine) as session:
        owner = User(device_id="owner", plan="free")
        session.add(owner)
        session.commit()
        session.refresh(owner)
        alert = _make_alert(owner.id)
        session.add(alert)
        session.commit()
        session.refresh(alert)
        session.add(
            SignalPerformance(
                user_id=owner.id,
                alert_id=alert.id,
                ticker=alert.ticker,
                action=alert.action,
                formula_score=alert.signal_score,
                claude_confidence=alert.confidence,
                action_strength=alert.action_strength,
                action_label=alert.action_label,
                price_at_alert=alert.price_at_alert,
                suggested_amount=alert.suggested_amount,
                outcome="took_trade",
            )
        )
        session.commit()
        alert_id = alert.id

    response = client.get(f"/alerts/{alert_id}/outcome", headers={"device-id": "attacker"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found."


def test_close_trade_cannot_close_another_users_record(client, db_engine):
    settings.app_mode = "public"
    with Session(db_engine) as session:
        owner = User(device_id="close-owner", plan="free")
        session.add(owner)
        session.commit()
        session.refresh(owner)
        alert = _make_alert(owner.id, ticker="VUAG")
        session.add(alert)
        session.commit()
        session.refresh(alert)
        session.add(
            SignalPerformance(
                user_id=owner.id,
                alert_id=alert.id,
                ticker=alert.ticker,
                action=alert.action,
                formula_score=alert.signal_score,
                claude_confidence=alert.confidence,
                action_strength=alert.action_strength,
                action_label=alert.action_label,
                price_at_alert=alert.price_at_alert,
                suggested_amount=alert.suggested_amount,
                outcome="took_trade",
                manual_entry_price=100,
                manual_amount=50,
            )
        )
        session.commit()
        alert_id = alert.id

    response = client.patch(
        f"/alerts/{alert_id}/outcome/close",
        headers={"device-id": "close-attacker"},
        json={"manual_exit_price": 101},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found."


def test_record_outcome_only_updates_current_users_performance(client, db_engine):
    settings.app_mode = "public"
    with Session(db_engine) as session:
        owner = User(device_id="record-owner", plan="free")
        session.add(owner)
        session.commit()
        session.refresh(owner)
        alert = _make_alert(owner.id, ticker="IITU")
        session.add(alert)
        session.commit()
        session.refresh(alert)
        session.add(
            SignalPerformance(
                user_id=owner.id,
                alert_id=alert.id,
                ticker=alert.ticker,
                action=alert.action,
                formula_score=alert.signal_score,
                claude_confidence=alert.confidence,
                action_strength=alert.action_strength,
                action_label=alert.action_label,
                price_at_alert=alert.price_at_alert,
                suggested_amount=alert.suggested_amount,
                outcome="watching",
            )
        )
        session.commit()
        alert_id = alert.id
        owner_id = owner.id

    response = client.post(
        f"/alerts/{alert_id}/outcome",
        headers={"device-id": "record-owner"},
        json={"outcome": "ignored"},
    )

    assert response.status_code == 200
    with Session(db_engine) as session:
        perf = session.exec(
            select(SignalPerformance).where(
                SignalPerformance.alert_id == alert_id,
                SignalPerformance.user_id == owner_id,
            )
        ).first()
    assert perf is not None
    assert perf.outcome == "ignored"


def test_push_disabled_does_not_log_warning(caplog):
    settings.enable_push_notifications = False
    settings.firebase_service_account_path = "missing.json"

    assert notification_service._init_firebase() is False

    assert not [record for record in caplog.records if record.levelname == "WARNING"]


def test_push_enabled_missing_path_logs_warning(caplog):
    settings.enable_push_notifications = True
    settings.firebase_service_account_path = "missing.json"

    assert notification_service._init_firebase() is False

    assert any(record.levelname == "WARNING" for record in caplog.records)
