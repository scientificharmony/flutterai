"""
Deterministic formula engine.
Scores a ticker 0–100 based on technical indicators.
Only candidates with score >= MIN_SIGNAL_SCORE are passed to Claude.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from services.market_data import get_ohlcv, OHLCVData
from services.indicators import compute_all


@dataclass
class ScoredCandidate:
    ticker: str
    score: float
    current_price: float
    rsi: float
    sma20: float
    sma50: float
    atr: float
    volume_ratio: float
    signal_summary: str


def score_candidate(ticker: str) -> Optional[ScoredCandidate]:
    """
    Fetch market data and compute a signal score for ticker.
    Returns None if data is unavailable or indicators cannot be computed.
    """
    data = get_ohlcv(ticker)
    if data is None:
        return None

    df = compute_all(data.df)
    latest = df.iloc[-1]

    # Guard against NaN indicators (insufficient history)
    for col in ["SMA20", "SMA50", "RSI14", "ATR14"]:
        if pd.isna(latest[col]):
            return None

    close = float(latest["Close"])
    sma20 = float(latest["SMA20"])
    sma50 = float(latest["SMA50"])
    current_rsi = float(latest["RSI14"])
    atr_val = float(latest["ATR14"])
    vol_ratio = float(latest["VolumeRatio"])

    score = 0.0
    reasons: list[str] = []

    # RSI in emerging-from-oversold zone (BUY bias)
    if 30 <= current_rsi <= 45:
        score += 25
        reasons.append(f"RSI {current_rsi:.1f} in recovery zone")
    elif 45 < current_rsi <= 55:
        score += 15
        reasons.append(f"RSI {current_rsi:.1f} neutral")
    elif current_rsi < 30:
        score += 10
        reasons.append(f"RSI {current_rsi:.1f} oversold")

    # Price vs SMA20
    pct_from_sma20 = (close - sma20) / sma20
    if 0 <= pct_from_sma20 <= 0.03:
        score += 20
        reasons.append("Price just above SMA20 (tight)")
    elif pct_from_sma20 > 0.03:
        score += 8
        reasons.append("Price above SMA20")
    elif -0.02 <= pct_from_sma20 < 0:
        score += 5
        reasons.append("Price near SMA20 (support test)")

    # Trend: SMA20 vs SMA50
    if sma20 > sma50:
        score += 15
        reasons.append("SMA20 > SMA50 (uptrend)")
    elif sma20 > sma50 * 0.98:
        score += 5
        reasons.append("SMA20 near SMA50")

    # Volume spike
    if vol_ratio >= 2.0:
        score += 15
        reasons.append(f"Volume spike {vol_ratio:.1f}x average")
    elif vol_ratio >= 1.5:
        score += 10
        reasons.append(f"Volume elevated {vol_ratio:.1f}x")
    elif vol_ratio >= 1.2:
        score += 5
        reasons.append(f"Volume slightly above average")

    # ATR: healthy volatility range (1–4% of price)
    atr_pct = atr_val / close if close > 0 else 0
    if 0.01 <= atr_pct <= 0.04:
        score += 15
        reasons.append(f"ATR {atr_pct*100:.1f}% (healthy range)")
    elif atr_pct < 0.01:
        score += 3
        reasons.append("ATR very low (low volatility)")

    # Penalty: extreme RSI overbought
    if current_rsi > 75:
        score -= 15
        reasons.append(f"RSI {current_rsi:.1f} overbought — penalty")

    score = max(0.0, min(100.0, score))

    return ScoredCandidate(
        ticker=ticker,
        score=round(score, 2),
        current_price=close,
        rsi=current_rsi,
        sma20=sma20,
        sma50=sma50,
        atr=atr_val,
        volume_ratio=vol_ratio,
        signal_summary="; ".join(reasons),
    )


def scan_watchlist(
    tickers: list[str], min_score: float = 75.0
) -> list[ScoredCandidate]:
    """
    Score all tickers, filter by min_score, return sorted descending.
    """
    results: list[ScoredCandidate] = []
    for ticker in tickers:
        candidate = score_candidate(ticker)
        if candidate and candidate.score >= min_score:
            results.append(candidate)
    results.sort(key=lambda c: c.score, reverse=True)
    return results
