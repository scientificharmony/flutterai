from fastapi import APIRouter, Depends

from auth import get_current_user
from models.db_models import User
from models.schemas import CfdScanRequest, CfdSummaryResponse
from services.cfd_service import get_cfd_summary

router = APIRouter(prefix="/cfd", tags=["cfd"])


@router.get("/summary", response_model=CfdSummaryResponse)
def cfd_summary(_: User = Depends(get_current_user)):
    return get_cfd_summary()


@router.post("/scan", response_model=CfdSummaryResponse)
def cfd_scan(
    body: CfdScanRequest,
    _: User = Depends(get_current_user),
):
    return get_cfd_summary(timeframe=body.timeframe, markets=body.markets or None)
