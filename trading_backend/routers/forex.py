from fastapi import APIRouter, Depends

from auth import get_current_user
from models.db_models import User
from models.schemas import ForexScanRequest, ForexSummaryResponse
from services.forex_service import get_forex_summary

router = APIRouter(prefix="/forex", tags=["forex"])


@router.get("/summary", response_model=ForexSummaryResponse)
def forex_summary(_: User = Depends(get_current_user)):
    return get_forex_summary()


@router.post("/scan", response_model=ForexSummaryResponse)
def forex_scan(
    body: ForexScanRequest,
    _: User = Depends(get_current_user),
):
    return get_forex_summary(timeframe=body.timeframe, pairs=body.pairs or None)
