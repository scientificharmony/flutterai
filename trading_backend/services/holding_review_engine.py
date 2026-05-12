from services.market_data import get_ohlcv
from services.indicators import compute_all


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def calculate_weakness_score(ticker: str) -> int | None:
    data = get_ohlcv(ticker, period="6mo")
    if not data or len(data.df) < 55:
        return None
    df = compute_all(data.df)
    latest = df.iloc[-1]
    prev20 = df.iloc[-21] if len(df) >= 21 else None

    score = 0.0
    if latest["Close"] < latest["SMA20"]:
        score += 18
    if latest["Close"] < latest["SMA50"]:
        score += 18
    if latest["SMA20"] < latest["SMA50"]:
        score += 16
    if latest["RSI14"] < 40:
        score += 16
    if prev20 is not None and prev20["Close"] > 0:
        ret20 = (latest["Close"] - prev20["Close"]) / prev20["Close"]
        if ret20 < 0:
            score += 16
    if len(df) >= 3:
        down_2d = latest["Close"] < df.iloc[-2]["Close"] < df.iloc[-3]["Close"]
        vol_rising = latest["VolumeRatio"] > df.iloc[-2]["VolumeRatio"]
        if down_2d and vol_rising:
            score += 16
    return _clamp(score)


def calculate_drawdown_risk_score(loss_pct: float) -> int:
    if loss_pct <= 0:
        return 0
    if loss_pct >= 25:
        return 100
    return _clamp((loss_pct / 25.0) * 100.0)


def calculate_exposure_risk_score(position_weight_pct: float, concentration_pct: float) -> int:
    # Size contributes 60%, concentration contributes 40%
    position_component = min(position_weight_pct, 20) / 20 * 100
    concentration_component = min(concentration_pct, 60) / 60 * 100
    return _clamp((position_component * 0.6) + (concentration_component * 0.4))
