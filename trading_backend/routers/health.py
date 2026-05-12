from fastapi import APIRouter
from models.schemas import HealthResponse
from config import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        claude_configured=bool(settings.ANTHROPIC_API_KEY),
        trading212_configured=bool(settings.T212_API_KEY),
        mode=settings.T212_ENV,
    )


@router.get("/")
def root():
    return {"status": "AI Trading Assistant API is live"}
