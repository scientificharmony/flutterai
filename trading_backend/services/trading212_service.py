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


def _request_kwargs() -> dict:
    """
    Trading 212 API keys can be configured as either a single token or an
    API-key/secret pair. Prefer basic auth when a secret is present because
    that is how the verified curl command authenticates in private testing.
    """
    if settings.T212_SECRET:
        return {"auth": (settings.T212_API_KEY, settings.T212_SECRET)}
    return {"headers": {"Authorization": settings.T212_API_KEY}}


def _normalise_symbol(symbol: str) -> str:
    return symbol.upper().strip()


def _ticker_aliases(inst: dict) -> set[str]:
    aliases: set[str] = set()
    for key in ("ticker", "shortName", "displayTicker", "symbol"):
        value = inst.get(key)
        if isinstance(value, str) and value.strip():
            clean = _normalise_symbol(value)
            aliases.add(clean)
            if "_" in clean:
                aliases.add(clean.split("_", 1)[0])
    return aliases


def _instrument_type(inst: dict) -> str:
    for key in ("type", "instrumentType"):
        value = inst.get(key)
        if isinstance(value, str) and value.strip():
            return value.upper().strip()
    return "UNKNOWN"


async def fetch_balance() -> float:
    """
    Return free cash balance from T212. Raises on failure — no fallback.
    Caller must handle and return HTTP 503.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{settings.t212_base_url}/equity/account/cash",
            **_request_kwargs(),
        )
        r.raise_for_status()
        data = r.json()
        return float(data.get("free", data.get("cash", 0)))


async def _fetch_instruments() -> list[dict]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{settings.t212_base_url}/equity/metadata/instruments",
            **_request_kwargs(),
        )
        r.raise_for_status()
        return r.json()


async def get_instruments() -> list[dict]:
    """Return cached instrument list, refreshing if stale."""
    global _instruments_cache, _instruments_fetched_at
    if time.time() - _instruments_fetched_at > _INSTRUMENT_CACHE_TTL:
        instruments = await _fetch_instruments()
        exact_index = {
            _normalise_symbol(inst["ticker"]): inst
            for inst in instruments
            if isinstance(inst.get("ticker"), str)
        }

        alias_buckets: dict[str, list[dict]] = {}
        for inst in instruments:
            for alias in _ticker_aliases(inst):
                alias_buckets.setdefault(alias, []).append(inst)

        # Only add aliases that resolve to one instrument. Ambiguous aliases
        # are intentionally left out so we never validate the wrong product.
        alias_index = {
            alias: matches[0]
            for alias, matches in alias_buckets.items()
            if len({m.get("ticker") for m in matches}) == 1
        }

        _instruments_cache = {**alias_index, **exact_index}
        _instruments_fetched_at = time.time()
    return list(_instruments_cache.values())


async def validate_ticker(ticker: str) -> bool:
    """Return True if ticker exists and is tradable on T212 (any type)."""
    await get_instruments()
    inst = _instruments_cache.get(_normalise_symbol(ticker))
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
    inst = _instruments_cache.get(_normalise_symbol(ticker))
    if not inst:
        return False, "UNKNOWN"

    raw_type = _instrument_type(inst)

    if not inst.get("tradable", True):
        return False, raw_type

    if raw_type in REJECTED_INSTRUMENT_TYPES:
        return False, raw_type

    if raw_type not in ALLOWED_INSTRUMENT_TYPES:
        return False, raw_type

    return True, raw_type


def get_instrument_name(ticker: str) -> str:
    """Return the human-readable name for a ticker, or the ticker itself."""
    inst = _instruments_cache.get(ticker.upper(), {})
    return inst.get("name", ticker)


def get_t212_ticker(ticker: str) -> str | None:
    """Return the canonical T212 ticker (e.g. 'AAPL_US_EQ') for a normalised ticker."""
    inst = _instruments_cache.get(_normalise_symbol(ticker))
    return inst.get("ticker") if inst else None


async def create_pie(
    name: str,
    slices: list[dict],
    dividend_action: str = "REINVEST",
) -> dict:
    """
    Create a pie in the user's T212 account via POST /equity/pies.
    slices: list of {"ticker": str, "allocation_percent": float}
    Raises ValueError for unmappable tickers, httpx.HTTPStatusError on API rejection.
    """
    instrument_shares: dict[str, float] = {}
    for s in slices:
        t212_ticker = get_t212_ticker(s["ticker"])
        if t212_ticker is None:
            raise ValueError(f"Cannot resolve T212 ticker for {s['ticker']!r}. "
                             "Refresh the instrument list and try again.")
        instrument_shares[t212_ticker] = round(s["allocation_percent"] / 100.0, 6)

    payload = {
        "name": name,
        "dividendCashAction": dividend_action,
        "instrumentShares": instrument_shares,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{settings.t212_base_url}/equity/pies",
            json=payload,
            **_request_kwargs(),
        )
        r.raise_for_status()
        return r.json()
