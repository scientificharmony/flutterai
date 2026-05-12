"""
Trading 212 API client.
- Fetches account cash balance (no order endpoints used).
- Validates tickers against T212 tradable Invest instruments only.
- Instrument list is cached for 1 hour.
"""
import time
from typing import Optional
import httpx

from config import settings
from models.pie_schemas import ALLOWED_INSTRUMENT_TYPES, REJECTED_INSTRUMENT_TYPES

_instruments_cache: dict[str, dict] = {}
_instruments_fetched_at: float = 0.0
_INSTRUMENT_CACHE_TTL = 3600  # 1 hour


def _headers() -> dict[str, str]:
    return {"Authorization": settings.T212_API_KEY}


async def fetch_balance() -> float:
    """
    Return free cash balance from T212. Raises on failure — no fallback.
    Caller must handle and return HTTP 503.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{settings.t212_base_url}/equity/account/cash",
            headers=_headers(),
        )
        r.raise_for_status()
        data = r.json()
        return float(data.get("free", data.get("cash", 0)))


async def _fetch_instruments() -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{settings.t212_base_url}/equity/metadata/instruments",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_instruments() -> list[dict]:
    """Return cached instrument list, refreshing if stale."""
    global _instruments_cache, _instruments_fetched_at
    if time.time() - _instruments_fetched_at > _INSTRUMENT_CACHE_TTL:
        instruments = await _fetch_instruments()
        _instruments_cache = {inst["ticker"]: inst for inst in instruments}
        _instruments_fetched_at = time.time()
    return list(_instruments_cache.values())


async def validate_ticker(ticker: str) -> bool:
    """Return True if ticker exists and is tradable on T212 (any type)."""
    await get_instruments()
    inst = _instruments_cache.get(ticker.upper())
    if not inst:
        return False
    return bool(inst.get("tradable", True))


async def validate_invest_instrument(ticker: str) -> tuple[bool, str]:
    """
    Return (valid, instrument_type).
    Valid means: exists on T212, tradable, and type is STOCK or ETF.
    Rejects CFD, FOREX, CRYPTO, OPTION, LEVERAGED, SHORT, UNKNOWN.
    """
    await get_instruments()
    inst = _instruments_cache.get(ticker.upper())
    if not inst:
        return False, "UNKNOWN"

    if not inst.get("tradable", True):
        return False, inst.get("type", "UNKNOWN")

    raw_type = str(inst.get("type", "UNKNOWN")).upper()

    if raw_type in REJECTED_INSTRUMENT_TYPES:
        return False, raw_type

    if raw_type not in ALLOWED_INSTRUMENT_TYPES:
        return False, raw_type

    return True, raw_type


def get_instrument_name(ticker: str) -> str:
    """Return the human-readable name for a ticker, or the ticker itself."""
    inst = _instruments_cache.get(ticker.upper(), {})
    return inst.get("name", ticker)
