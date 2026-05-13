from config import settings
from models.schemas import ForexSignalResponse, ForexSummaryResponse

DEFAULT_FOREX_PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "EUR/GBP",
    "AUD/USD",
    "USD/CHF",
    "GBP/JPY",
]


_MOCK_PRICES = {
    "EUR/USD": 1.0824,
    "GBP/USD": 1.2710,
    "USD/JPY": 156.82,
    "EUR/GBP": 0.8516,
    "AUD/USD": 0.6640,
    "USD/CHF": 0.9035,
    "GBP/JPY": 199.35,
}


def provider_connected() -> bool:
    if settings.FOREX_PROVIDER.lower() != "ig":
        return False
    return bool(settings.IG_API_KEY and settings.IG_USERNAME and settings.IG_PASSWORD)


def risk_amount() -> float:
    return round(settings.FOREX_DEMO_BALANCE * (settings.FOREX_RISK_BPS / 10000), 2)


def _pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("/JPY") else 0.0001


def _mock_strength(pair: str, timeframe: str) -> int:
    seed = sum(ord(ch) for ch in f"{pair}:{timeframe}")
    return 60 + (seed % 24)


def _mock_direction(pair: str, strength: int) -> str:
    if strength < settings.FOREX_MIN_SIGNAL_STRENGTH:
        return "NO_TRADE"
    return "LONG" if sum(ord(ch) for ch in pair) % 2 == 0 else "SHORT"


def build_mock_signal(pair: str, timeframe: str) -> ForexSignalResponse:
    price = _MOCK_PRICES.get(pair, 1.0)
    pip = _pip_size(pair)
    strength = _mock_strength(pair, timeframe)
    direction = _mock_direction(pair, strength)
    stop_pips = 25 if pair.endswith("/JPY") else 35
    target_pips = stop_pips * 2
    if direction == "SHORT":
        stop_loss = price + (stop_pips * pip)
        take_profit = price - (target_pips * pip)
    else:
        stop_loss = price - (stop_pips * pip)
        take_profit = price + (target_pips * pip)
    if direction == "NO_TRADE":
        stop_loss = price
        take_profit = price

    risk = risk_amount()
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
        position_units=0 if direction == "NO_TRADE" else int(max(1, risk / (stop_pips * pip))),
        rationale=(
            "Practice-only mock setup until an IG demo connector is configured."
            if direction != "NO_TRADE"
            else "No practice trade: signal strength is below the Forex Lab gate."
        ),
        invalidation="Do not use live funds. Ignore if spread widens or price moves beyond stop.",
    )


def get_forex_summary(timeframe: str = "15m", pairs: list[str] | None = None) -> ForexSummaryResponse:
    selected_pairs = pairs or DEFAULT_FOREX_PAIRS
    signals = [build_mock_signal(pair, timeframe) for pair in selected_pairs]
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
