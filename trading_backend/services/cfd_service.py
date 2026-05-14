import logging
from dataclasses import dataclass

import httpx

from config import settings
from models.schemas import CfdSignalResponse, CfdSummaryResponse
from services.forex_service import _get_ig_session, _ig_base_url, _ig_headers

logger = logging.getLogger(__name__)

DEFAULT_CFD_MARKETS = [
    "FTSE 100 Cash",
    "Germany 40 Cash",
    "Wall Street Cash",
    "US Tech 100 Cash",
    "Oil - Brent Crude",
    "Apple Inc",
    "Amazon.com Inc",
    "Tesla Motors Inc",
]

_MOCK_CFD_PRICES = {
    "FTSE 100 Cash": 10342.0,
    "Germany 40 Cash": 24455.0,
    "Wall Street Cash": 49952.0,
    "US Tech 100 Cash": 25600.0,
    "Oil - Brent Crude": 10552.0,
    "Apple Inc": 298.0,
    "Amazon.com Inc": 267.0,
    "Tesla Motors Inc": 445.0,
}


@dataclass
class CfdMarketSnapshot:
    market: str
    price: float
    bid: float | None
    offer: float | None
    epic: str | None
    market_status: str | None
    source: str


def provider_connected() -> bool:
    return bool(
        settings.FOREX_PROVIDER.lower() == "ig"
        and settings.IG_API_KEY
        and settings.IG_USERNAME
        and settings.IG_PASSWORD
    )


def risk_amount() -> float:
    return round(settings.FOREX_DEMO_BALANCE * (settings.FOREX_RISK_BPS / 10000), 2)


def _mock_snapshot(market: str) -> CfdMarketSnapshot:
    return CfdMarketSnapshot(
        market=market,
        price=_MOCK_CFD_PRICES.get(market, 100.0),
        bid=None,
        offer=None,
        epic=None,
        market_status=None,
        source="mock",
    )


def _search_ig_market(market: str) -> str | None:
    session = _get_ig_session()
    response = httpx.get(
        f"{_ig_base_url()}/markets",
        headers=_ig_headers(session=session),
        params={"searchTerm": market},
        timeout=12.0,
    )
    response.raise_for_status()
    markets = response.json().get("markets", [])
    if not markets:
        return None

    market_key = _normalise(market)
    preferred = None
    for item in markets:
        epic = item.get("epic")
        name = _normalise(item.get("instrumentName"))
        if not epic:
            continue
        if market_key in name or name in market_key:
            return epic
        preferred = preferred or epic
    return preferred


def _normalise(value: str | None) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _ig_snapshot(market: str) -> CfdMarketSnapshot | None:
    session = _get_ig_session()
    epic = _search_ig_market(market)
    if not epic:
        return None
    response = httpx.get(
        f"{_ig_base_url()}/markets/{epic}",
        headers=_ig_headers(version="3", session=session),
        timeout=12.0,
    )
    response.raise_for_status()
    data = response.json()
    snapshot = data.get("snapshot", {})
    bid = snapshot.get("bid")
    offer = snapshot.get("offer")
    if bid is not None and offer is not None:
        price = (float(bid) + float(offer)) / 2
    elif bid is not None:
        price = float(bid)
    elif offer is not None:
        price = float(offer)
    else:
        return None
    return CfdMarketSnapshot(
        market=market,
        price=price,
        bid=float(bid) if bid is not None else None,
        offer=float(offer) if offer is not None else None,
        epic=epic,
        market_status=snapshot.get("marketStatus"),
        source="ig",
    )


def _market_snapshots(markets: list[str]) -> list[CfdMarketSnapshot]:
    if settings.FOREX_PROVIDER.lower() == "mock":
        return [_mock_snapshot(market) for market in markets]
    if not provider_connected():
        logger.warning("IG CFD provider credentials are incomplete; no CFD snapshots returned.")
        return []

    snapshots = []
    for market in markets:
        try:
            snapshot = _ig_snapshot(market)
        except Exception as exc:
            logger.warning("IG CFD snapshot fetch failed for %s; skipping market: %s", market, exc)
            snapshot = None
        if snapshot:
            snapshots.append(snapshot)
        else:
            logger.info("IG CFD snapshot unavailable for %s; market skipped.", market)
    return snapshots


def _strength(market: str, timeframe: str) -> int:
    seed = sum(ord(ch) for ch in f"cfd:{market}:{timeframe}")
    return 60 + (seed % 25)


def _direction(market: str, strength: int) -> str:
    if strength < settings.FOREX_MIN_SIGNAL_STRENGTH:
        return "NO_TRADE"
    return "LONG" if sum(ord(ch) for ch in market) % 2 == 0 else "SHORT"


def _stop_points(price: float) -> float:
    if price >= 10000:
        return 80.0
    if price >= 1000:
        return 35.0
    return max(round(price * 0.015, 2), 1.0)


def build_signal(snapshot: CfdMarketSnapshot, timeframe: str) -> CfdSignalResponse:
    strength = _strength(snapshot.market, timeframe)
    direction = _direction(snapshot.market, strength)
    stop_points = _stop_points(snapshot.price)
    target_points = stop_points * 2
    if direction == "LONG":
        stop_loss = snapshot.price - stop_points
        take_profit = snapshot.price + target_points
    elif direction == "SHORT":
        stop_loss = snapshot.price + stop_points
        take_profit = snapshot.price - target_points
    else:
        stop_loss = snapshot.price
        take_profit = snapshot.price

    return CfdSignalResponse(
        market=snapshot.market,
        epic=snapshot.epic,
        direction=direction,
        strength=strength,
        timeframe=timeframe,
        entry=round(snapshot.price, 2),
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        risk_reward=2.0 if direction != "NO_TRADE" else 0.0,
        risk_amount=risk_amount(),
        contract_size=0.1 if direction != "NO_TRADE" else 0.0,
        rationale=(
            f"Practice-only IG demo CFD snapshot. Market status: {snapshot.market_status or 'unknown'}."
            if direction != "NO_TRADE"
            else "No practice CFD trade: signal strength is below the CFD Lab gate."
        ),
        invalidation="Do not use live funds. Ignore if spread widens or price moves beyond stop.",
    )


def get_cfd_summary(timeframe: str = "15m", markets: list[str] | None = None) -> CfdSummaryResponse:
    selected_markets = markets or DEFAULT_CFD_MARKETS
    snapshots = _market_snapshots(selected_markets)
    signals = [build_signal(snapshot, timeframe) for snapshot in snapshots]
    signals.sort(key=lambda signal: signal.strength, reverse=True)
    return CfdSummaryResponse(
        provider=settings.FOREX_PROVIDER,
        connected=provider_connected(),
        account_type=settings.IG_ACCOUNT_TYPE if settings.FOREX_PROVIDER.lower() == "ig" else "MOCK",
        demo_balance=settings.FOREX_DEMO_BALANCE,
        risk_bps=settings.FOREX_RISK_BPS,
        risk_amount=risk_amount(),
        min_signal_strength=settings.FOREX_MIN_SIGNAL_STRENGTH,
        markets=selected_markets,
        signals=signals,
    )
