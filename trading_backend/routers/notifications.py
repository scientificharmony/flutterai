from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from auth import get_current_user
from database import get_session
from models.db_models import User, DeviceToken
from models.schemas import RegisterTokenRequest

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/register-token")
def register_token(
    body: RegisterTokenRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    existing = session.exec(
        select(DeviceToken).where(DeviceToken.token == body.token)
    ).first()
    if not existing:
        token = DeviceToken(
            user_id=user.id, token=body.token, platform=body.platform
        )
        session.add(token)
        session.commit()
    return {"status": "registered"}
