"""
Auth abstraction layer.
In private_test mode: always returns the single TEST_USER_ID user (plan=pro).
In public mode: device-id header → User row (MVP, replace with JWT later).
"""
from fastapi import Header, Depends, HTTPException
from sqlmodel import Session, select

from config import settings
from database import get_session
from models.db_models import User


def _get_or_create(device_id: str, plan: str, session: Session) -> User:
    user = session.exec(select(User).where(User.device_id == device_id)).first()
    if not user:
        user = User(device_id=device_id, plan=plan)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def get_current_user(
    device_id: str | None = Header(default=None),
    session: Session = Depends(get_session),
) -> User:
    if settings.is_private_test:
        return _get_or_create(settings.TEST_USER_ID, "pro", session)
    if device_id is None or not device_id.strip():
        raise HTTPException(status_code=401, detail="device-id header is required.")
    return _get_or_create(device_id, "free", session)


def require_admin(x_admin_token: str | None = Header(default=None)) -> bool:
    if not settings.enable_admin_routes:
        raise HTTPException(status_code=404, detail="Not found.")
    if not settings.admin_api_token:
        raise HTTPException(status_code=403, detail="Admin API token is not configured.")
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=403, detail="Admin access denied.")
    return True
