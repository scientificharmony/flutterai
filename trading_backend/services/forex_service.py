import logging
from dataclasses import dataclass
from time import monotonic

import httpx
import pandas as pd

from config import settings
from models.schemas import ForexSignalResponse, ForexSummaryResponse
from services.indicators import compute_all
from services.market_data import get_forex_ohlcv

logger = logging.getLogger(__name__)

DEFAULT_FOREX_PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "EUR/GBP",
    "AUD/USD",
    "USD/CHF",
    "GBP/JPY",
    "EUR/JPY",
    "AUD/JPY",
    "NZD/USD",
    "USD/CAD",
    "EUR/CHF",
    "EUR/AUD",
    "GBP/CHF",
    "GBP/AUD",
    "CAD/JPY",
    "CHF/JPY",
    "AUD/NZD",
    "EUR/CAD",
    "GBP/CAD",
]


_MOCK_PRICES = {
    "EUR/USD": 1.0824,
    "GBP/USD": 1.2710,
    "USD/JPY": 156.82,
    "EUR/GBP": 0.8516,
    "AUD/USD": 0.6640,
    "USD/CHF": 0.9035,
    "GBP/JPY": 199.35,
    "EUR/JPY": 169.80,
    "AUD/JPY": 104.20,
    "NZD/USD": 0.6120,
    "USD/CAD": 1.3720,
    "EUR/CHF": 0.9480,
    "EUR/AUD": 1.6300,
    "GBP/CHF": 1.1140,
    "GBP/AUD": 1.9140,
    "CAD/JPY": 115.10,
    "CHF/JPY": 179.00,
    "AUD/NZD": 1.0860,
    "EUR/CAD": 1.4860,
    "GBP/CAD": 1.7440,
}

IG_DEMO_BASE_URL = "https://demo-api.ig.com/gateway/deal"
IG_LIVE_BASE_URL = "https://api.ig.com/gateway/deal"


@dataclass
class IgSession:
    cst: str
    security_token: str
    account_id: str | None
    expires_at: float


@dataclass
class ForexMarketSnapshot:
    pair: str
    price: float
    bid: float | None
    offer: float | None
    epic: str | None
    market_status: str | None
    source: str


@dataclass
class IgOpenPosition:
    deal_id: str
    epic: str
    direction: str
    size: float
    level: float | None = None
    stop_level: float | None = None
    limit_level: float | None = None
    created_date: str | None = None
    instrument_name: str | None = None


@dataclass
class IgPlacedPosition:
    deal_id: str
    deal_reference: str
    epic: str
    direction: str
    size: float


_ig_session: IgSession | None = None
_epic_cache: dict[str, str] = {}
_snapshot_cache: dict[str, tuple[ForexMarketSnapshot, float]] = {}
_SNAPSHOT_CACHE_SECONDS = 60.0


def provider_connected() -> bool:
    if settings.FOREX_PROVIDER.lower() != "ig":
        return False
    return bool(settings.IG_API_KEY and settings.IG_USERNAME and settings.IG_PASSWORD)


def risk_amount() -> float:
    return round(settings.FOREX_DEMO_BALANCE * (settings.FOREX_RISK_BPS / 10000), 2)


def _pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("/JPY") else 0.0001


def _fallback_strength(pair: str, timeframe: str) -> int:
    """Deterministic fallback used only when OHLCV data is unavailable."""
    seed = sum(ord(ch) for ch in f"{pair}:{timeframe}")
    return 60 + (seed % 24)


def _score_rsi(rsi_val: float, direction: str) -> float:
    """Score RSI 0–30 based on how well it supports the direction."""
    if direction == "LONG":
        if 40 <= rsi_val <= 65:
            return 30.0
        if 30 <= rsi_val < 40:
            return (rsi_val - 30) / 10 * 30
        if 65 < rsi_val <= 70:
            return (70 - rsi_val) / 5 * 30
        return 0.0
    else:  # SHORT
        if 35 <= rsi_val <= 60:
            return 30.0
        if 60 < rsi_val <= 70:
            return (70 - rsi_val) / 10 * 30
        if 30 <= rsi_val < 35:
            return (rsi_val - 30) / 5 * 30
        return 0.0


def _real_signal(pair: str) -> tuple[int, str]:
    """
    Calculate signal strength (0–100) and direction from real indicators.

    Scoring breakdown:
      Trend  — SMA20 vs SMA50 gap strength  40 pts
      RSI    — RSI14 position for direction  30 pts
      Price  — close vs SMA20               20 pts
      ATR    — volatility within normal band 10 pts

    Returns (strength, direction). Falls back to deterministic mock
    if OHLCV data is unavailable or indicators cannot be computed.
    """
    data = get_forex_ohlcv(pair)
    if data is None or len(data.df) < 50:
        fb = _fallback_strength(pair, "1h")
        return fb, ("NO_TRADE" if fb < settings.FOREX_MIN_SIGNAL_STRENGTH else "LONG")

    df = compute_all(data.df)
    last = df.iloc[-1]

    sma20 = last.get("SMA20")
    sma50 = last.get("SMA50")
    rsi14 = last.get("RSI14")
    atr14 = last.get("ATR14")
    price = float(last["Close"])

    if pd.isna(sma20) or pd.isna(sma50) or pd.isna(rsi14):
        fb = _fallback_strength(pair, "1h")
        return fb, ("NO_TRADE" if fb < settings.FOREX_MIN_SIGNAL_STRENGTH else "LONG")

    gap_pct = abs(float(sma20) - float(sma50)) / float(sma50) * 100
    if gap_pct < 0.03:
        return 40, "NO_TRADE"

    direction = "LONG" if float(sma20) > float(sma50) else "SHORT"

    trend_score = min(40.0, gap_pct / 0.5 * 40)
    rsi_score = _score_rsi(float(rsi14), direction)
    price_score = 20.0 if (direction == "LONG" and price > float(sma20)) or (direction == "SHORT" and price < float(sma20)) else 0.0

    atr_score = 0.0
    if not pd.isna(atr14) and float(atr14) > 0:
        atr_series = df["ATR14"].dropna()
        if len(atr_series) >= 20:
            avg_atr = float(atr_series.iloc[-20:].mean())
            if avg_atr > 0:
                ratio = float(atr14) / avg_atr
                if 0.5 <= ratio <= 2.0:
                    atr_score = 10.0
                elif 0.3 <= ratio < 0.5 or 2.0 < ratio <= 3.0:
                    atr_score = 5.0

    strength = int(round(min(100.0, max(0.0, trend_score + rsi_score + price_score + atr_score))))
    if strength < settings.FOREX_MIN_SIGNAL_STRENGTH:
        direction = "NO_TRADE"

    return strength, direction


def _atr_stops(df: pd.DataFrame, direction: str, price: float, pair: str) -> tuple[float, float]:
    """
    Calculate stop loss and take profit using ATR14 (1.5× stop, 3× TP = 2:1 RR).
    Falls back to static pip offsets if ATR is unavailable.
    """
    pip = _pip_size(pair)
    fallback_stop_pips = 25 if pair.endswith("/JPY") else 35

    try:
        atr14 = float(df["ATR14"].dropna().iloc[-1])
    except Exception:
        atr14 = 0.0

    if atr14 > 0:
        stop_dist = atr14 * 1.5
        tp_dist = atr14 * 3.0
    else:
        stop_dist = fallback_stop_pips * pip
        tp_dist = fallback_stop_pips * 2 * pip

    if direction == "LONG":
        return price - stop_dist, price + tp_dist
    else:
        return price + stop_dist, price - tp_dist


def _ig_base_url() -> str:
    return IG_DEMO_BASE_URL if settings.IG_ACCOUNT_TYPE.upper() == "DEMO" else IG_LIVE_BASE_URL


def _ig_headers(version: str = "1", session: IgSession | None = None) -> dict[str, str]:
    headers = {
        "X-IG-API-KEY": settings.IG_API_KEY,
        "Version": version,
        "Content-Type": "application/json",
        "Accept": "application/json; charset=UTF-8",
    }
    if session:
        headers["CST"] = session.cst
        headers["X-SECURITY-TOKEN"] = session.security_token
        if session.account_id:
            headers["IG-ACCOUNT-ID"] = session.account_id
    return headers


def _get_ig_session() -> IgSession:
    global _ig_session
    if _ig_session and _ig_session.expires_at > monotonic() + 60:
        return _ig_session

    response = httpx.post(
        f"{_ig_base_url()}/session",
        headers=_ig_headers(version="2"),
        json={"identifier": settings.IG_USERNAME, "password": settings.IG_PASSWORD},
        timeout=12.0,
    )
    response.raise_for_status()
    data = response.json()
    _ig_session = IgSession(
        cst=response.headers.get("CST", ""),
        security_token=response.headers.get("X-SECURITY-TOKEN", ""),
        account_id=data.get("currentAccountId") or data.get("accountId"),
        expires_at=monotonic() + 60 * 60 * 6,
    )
    if not _ig_session.cst or not _ig_session.security_token:
        raise RuntimeError("IG login did not return session tokens")
    return _ig_session


def _search_ig_epic(pair: str, session: IgSession) -> str | None:
    if pair in _epic_cache:
        return _epic_cache[pair]

    search_term = pair.replace("/", "")
    response = httpx.get(
        f"{_ig_base_url()}/markets",
        headers=_ig_headers(session=session),
        params={"searchTerm": search_term},
        timeout=12.0,
    )
    response.raise_for_status()
    markets = response.json().get("markets", [])
    preferred = None
    for market in markets:
        epic = market.get("epic")
        name = f"{market.get('instrumentName', '')} {market.get('expiry', '')}".upper()
        instrument_type = str(market.get("instrumentType", "")).upper()
        if not epic:
            continue
        if pair.replace("/", "") in name.replace("/", "").replace(" ", ""):
            preferred = epic
            if "CURRENC" in instrument_type or "FOREX" in instrument_type or "DFB" in name:
                break
    if preferred:
        _epic_cache[pair] = preferred
    return preferred


def _ig_snapshot(pair: str, session: IgSession) -> ForexMarketSnapshot | None:
    cached = _snapshot_cache.get(pair)
    if cached and cached[1] > monotonic():
        return cached[0]

    epic = _search_ig_epic(pair, session)
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
    price = None
    if bid is not None and offer is not None:
        price = (float(bid) + float(offer)) / 2
    elif bid is not None:
        price = float(bid)
    elif offer is not None:
        price = float(offer)
    if price is None:
        return None
    market_snapshot = ForexMarketSnapshot(
        pair=pair,
        price=price,
        bid=float(bid) if bid is not None else None,
        offer=float(offer) if offer is not None else None,
        epic=epic,
        market_status=snapshot.get("marketStatus"),
        source="ig",
    )
    _snapshot_cache[pair] = (market_snapshot, monotonic() + _SNAPSHOT_CACHE_SECONDS)
    return market_snapshot


def _position_direction_for_signal(direction: str) -> str:
    return "BUY" if direction.upper() == "LONG" else "SELL"


def _close_direction_for_position(direction: str) -> str:
    return "SELL" if direction.upper() == "BUY" else "BUY"


def _close_direction_for_forex(direction: str) -> str:
    """
    Close direction for a forex position when we only know the signal direction
    (LONG/SHORT) rather than IG's BUY/SELL direction.

    LONG -> open was BUY -> close must be SELL
    SHORT -> open was SELL -> close must be BUY
    """
    d = (direction or "").upper()
    if d == "LONG":
        return "SELL"
    if d == "SHORT":
        return "BUY"
    return _close_direction_for_position(d)


def _normalise_market_text(value: str | None) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _position_matches_pair(pos: IgOpenPosition, pair: str, searched_epic: str | None) -> bool:
    if searched_epic and pos.epic == searched_epic:
        return True
    pair_key = _normalise_market_text(pair)
    return pair_key in _normalise_market_text(pos.epic) or pair_key in _normalise_market_text(pos.instrument_name)


def get_ig_open_positions() -> list[IgOpenPosition]:
    if not provider_connected():
        return []
    session = _get_ig_session()
    response = httpx.get(
        f"{_ig_base_url()}/positions",
        headers=_ig_headers(version="2", session=session),
        timeout=12.0,
    )
    response.raise_for_status()
    positions = []
    for item in response.json().get("positions", []):
        position = item.get("position", {})
        market = item.get("market", {})
        deal_id = position.get("dealId")
        epic = market.get("epic") or position.get("epic")
        direction = position.get("direction")
        size = position.get("size")
        level = position.get("level")
        stop_level = position.get("stopLevel")
        limit_level = position.get("limitLevel")
        instrument_name = market.get("instrumentName") or market.get("marketName") or market.get("name")
        if deal_id and epic and direction and size is not None:
            positions.append(
                IgOpenPosition(
                    deal_id=deal_id,
                    epic=epic,
                    direction=str(direction).upper(),
                    size=float(size),
                    level=float(level) if level is not None else None,
                    stop_level=float(stop_level) if stop_level is not None else None,
                    limit_level=float(limit_level) if limit_level is not None else None,
                    created_date=position.get("createdDate") or position.get("createdDateUTC"),
                    instrument_name=instrument_name,
                )
            )
    return positions


def infer_pair_from_ig_position(epic: str, instrument_name: str | None = None) -> str | None:
    """
    Best-effort mapping from IG epic/instrument text to our canonical 'AAA/BBB' pair.
    Used to sync IG-open positions back into Hey Jimmy tracking when the user places
    a trade manually on IG (or closes a tracked trade in-app by mistake).
    """
    dummy = IgOpenPosition(deal_id="x", epic=epic, direction="BUY", size=0.1, instrument_name=instrument_name)
    for pair in DEFAULT_FOREX_PAIRS:
        if _position_matches_pair(dummy, pair, searched_epic=None):
            return pair
    return None


def find_matching_ig_position(
    pair: str,
    direction: str,
    exclude_deal_ids: set[str] | None = None,
) -> IgOpenPosition | None:
    if not provider_connected():
        return None
    session = _get_ig_session()
    epic = _search_ig_epic(pair, session)
    expected_direction = _position_direction_for_signal(direction)
    exclude_deal_ids = exclude_deal_ids or set()
    matches = [
        pos for pos in get_ig_open_positions()
        if pos.deal_id not in exclude_deal_ids
        and pos.direction == expected_direction
        and _position_matches_pair(pos, pair, epic)
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda pos: pos.created_date or "", reverse=True)[0]


def _currency_code_for_pair(pair: str) -> str:
    if "/" not in pair:
        return "GBP"
    return pair.split("/", 1)[1].upper()


def place_ig_demo_position(
    pair: str,
    direction: str,
    size: float,
    stop_level: float,
    limit_level: float,
) -> IgPlacedPosition:
    if settings.IG_ACCOUNT_TYPE.upper() != "DEMO":
        raise RuntimeError("IG forex execution is only allowed for DEMO accounts")
    if size <= 0:
        raise RuntimeError("IG forex execution size must be greater than zero")

    session = _get_ig_session()
    epic = _search_ig_epic(pair, session)
    if not epic:
        raise RuntimeError(f"IG epic unavailable for {pair}")

    ig_direction = _position_direction_for_signal(direction)
    response = httpx.post(
        f"{_ig_base_url()}/positions/otc",
        headers=_ig_headers(version="2", session=session),
        json={
            "epic": epic,
            "expiry": "-",
            "direction": ig_direction,
            "size": size,
            "orderType": "MARKET",
            "currencyCode": _currency_code_for_pair(pair),
            "forceOpen": True,
            "guaranteedStop": False,
            "stopLevel": round(stop_level, 5),
            "limitLevel": round(limit_level, 5),
        },
        timeout=12.0,
    )
    response.raise_for_status()
    deal_reference = response.json().get("dealReference", "")
    deal_id = ""
    if deal_reference:
        # IG confirms endpoint can briefly return 404 right after placing a deal.
        # Retry a few times before giving up, then fall back to matching the deal
        # from the open positions list.
        confirm_data = None
        for attempt in range(4):
            try:
                confirm = httpx.get(
                    f"{_ig_base_url()}/confirms/{deal_reference}",
                    headers=_ig_headers(session=session),
                    timeout=12.0,
                )
                confirm.raise_for_status()
                confirm_data = confirm.json()
                deal_id = confirm_data.get("dealId") or ""
                break
            except Exception as exc:
                if attempt == 3:
                    logger.warning("IG demo deal confirm failed for %s: %s", deal_reference, exc)
                else:
                    # 0.25s, 0.5s, 0.75s backoff
                    import time
                    time.sleep(0.25 * (attempt + 1))

        if not deal_id:
            try:
                open_pos = get_ig_open_positions()
                candidates = [p for p in open_pos if p.epic == epic and p.direction == ig_direction and abs(p.size - size) < 1e-6]
                if candidates:
                    deal_id = candidates[0].deal_id
            except Exception:
                pass
    return IgPlacedPosition(
        deal_id=deal_id,
        deal_reference=deal_reference,
        epic=epic,
        direction=ig_direction,
        size=size,
    )


def close_ig_position(deal_id: str, direction: str, size: float) -> str:
    if settings.IG_ACCOUNT_TYPE.upper() != "DEMO":
        raise RuntimeError("IG auto-close is only allowed for DEMO accounts")
    session = _get_ig_session()
    response = httpx.request(
        "DELETE",
        f"{_ig_base_url()}/positions/otc",
        headers=_ig_headers(version="1", session=session),
        json={
            "dealId": deal_id,
            "direction": _close_direction_for_forex(direction),
            "orderType": "MARKET",
            "size": size,
        },
        timeout=12.0,
    )
    response.raise_for_status()
    return response.json().get("dealReference", "")


def _market_snapshots(pairs: list[str]) -> list[ForexMarketSnapshot]:
    def mock_snapshot(pair: str) -> ForexMarketSnapshot:
        return ForexMarketSnapshot(
            pair=pair,
            price=_MOCK_PRICES.get(pair, 1.0),
            bid=None,
            offer=None,
            epic=None,
            market_status=None,
            source="mock",
        )

    if settings.FOREX_PROVIDER.lower() == "mock":
        return [mock_snapshot(pair) for pair in pairs]

    if not provider_connected():
        logger.warning("IG forex provider is selected but credentials are incomplete; no forex snapshots returned.")
        return []

    try:
        session = _get_ig_session()
    except Exception as exc:
        logger.warning("IG forex login failed; no forex snapshots returned: %s", exc)
        return []

    snapshots = []
    for pair in pairs:
        try:
            snapshot = _ig_snapshot(pair, session)
        except Exception as exc:
            logger.warning("IG forex snapshot fetch failed for %s; skipping pair: %s", pair, exc)
            snapshot = None
        if snapshot:
            snapshots.append(snapshot)
        else:
            logger.info("IG forex snapshot unavailable for %s; pair skipped.", pair)
    return snapshots


def build_signal(snapshot: ForexMarketSnapshot, timeframe: str) -> ForexSignalResponse:
    pair = snapshot.pair
    price = snapshot.price
    pip = _pip_size(pair)

    strength, direction = _real_signal(pair)

    data = get_forex_ohlcv(pair)
    if data is not None and len(data.df) >= 50:
        df_ind = compute_all(data.df)
        stop_loss, take_profit = _atr_stops(df_ind, direction, price, pair)
    else:
        fallback_stop_pips = 25 if pair.endswith("/JPY") else 35
        if direction == "SHORT":
            stop_loss = price + (fallback_stop_pips * pip)
            take_profit = price - (fallback_stop_pips * 2 * pip)
        else:
            stop_loss = price - (fallback_stop_pips * pip)
            take_profit = price + (fallback_stop_pips * 2 * pip)

    if direction == "NO_TRADE":
        stop_loss = price
        take_profit = price

    stop_dist = abs(price - stop_loss)
    risk = risk_amount()
    position_units = 0 if direction == "NO_TRADE" or stop_dist == 0 else int(max(1, risk / stop_dist))

    return ForexSignalResponse(
        pair=pair,
        direction=direction,
        strength=strength,
        timeframe=timeframe,
        entry=round(price, 5),
        stop_loss=round(stop_loss, 5),
        take_profit=round(take_profit, 5),
        risk_reward=2.0 if direction != "NO_TRADE" else 0.0,
        risk_amount=risk,
        position_units=position_units,
        rationale=(
            (
                f"Signal based on SMA20/SMA50 trend, RSI14, and ATR14. "
                f"Strength {strength}/100. "
                f"Market status: {snapshot.market_status or 'unknown'}."
                if snapshot.source == "ig"
                else f"Signal based on SMA20/SMA50 trend, RSI14, and ATR14. Strength {strength}/100."
            )
            if direction != "NO_TRADE"
            else "No trade: signal strength below threshold or trend is unclear."
        ),
        invalidation="Do not use live funds. Ignore if spread widens or price moves beyond stop.",
    )


def get_forex_summary(timeframe: str = "15m", pairs: list[str] | None = None) -> ForexSummaryResponse:
    selected_pairs = pairs or DEFAULT_FOREX_PAIRS
    snapshots = _market_snapshots(selected_pairs)
    signals = [build_signal(snapshot, timeframe) for snapshot in snapshots]
    signals.sort(key=lambda signal: signal.strength, reverse=True)
    return ForexSummaryResponse(
        provider=settings.FOREX_PROVIDER,
        connected=provider_connected(),
        account_type=settings.IG_ACCOUNT_TYPE if settings.FOREX_PROVIDER.lower() == "ig" else "MOCK",
        demo_balance=settings.FOREX_DEMO_BALANCE,
        risk_bps=settings.FOREX_RISK_BPS,
        risk_amount=risk_amount(),
        min_signal_strength=settings.FOREX_MIN_SIGNAL_STRENGTH,
        pairs=selected_pairs,
        signals=signals,
    )


def get_forex_mid_price(pair: str) -> float | None:
    """Return the best available mid price for a pair without creating a signal."""
    snapshots = _market_snapshots([pair])
    if not snapshots:
        return None
    return snapshots[0].price
