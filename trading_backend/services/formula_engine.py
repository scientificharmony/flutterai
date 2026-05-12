"""
Deterministic formula engine.
Scores a ticker 0–100 based on technical indicators.
Only candidates with score >= MIN_SIGNAL_SCORE are passed to Claude.

ETF vs stock scoring:
  ETFs are broad diversified instruments — they don't spike in volume and
  have naturally low ATR as a % of price. Applying stock-tuned bands would
  structurally cap ETF scores below the actionable threshold even in good
  conditions. ETF mode uses wider ATR bands (0.3–2%) and lower volume
  thresholds (consistent flow rather than spikes).
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd

from services.market_data import get_ohlcv, OHLCVData
from services.indicators import compute_all

# Tickers known to be LSE-listed ETFs — same set as market_data._LSE_TICKERS.
_ETF_TICKERS: set[str] = {
    "VUSAL", "VUSAA", "VUSAS", "VUAG", "VWRP",
    "VHYLL", "VHYLA",
    "IITU", "IITUL",
    "EQQQL", "EQQQM", "EQQQS",
    "INRGL", "INRGS",
    "SWDA", "CSP1", "CNDX", "ISF", "VEVE",
}


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


def _score_rsi(rsi: float) -> tuple[float, str]:
    """Stock RSI scoring — rewards recovery from oversold."""
    if 30 <= rsi <= 45:
        return 25.0, f"RSI {rsi:.1f} in recovery zone"
    if 45 < rsi <= 55:
        return 15.0, f"RSI {rsi:.1f} neutral"
    if rsi < 30:
        return 10.0, f"RSI {rsi:.1f} oversold"
    return 0.0, ""


def _score_rsi_etf(rsi: float) -> tuple[float, str]:
    """ETF RSI scoring — rewards healthy momentum, not just oversold recovery.
    ETFs in a bull market routinely trade at RSI 55-75; that is a positive
    signal, not a warning. Only penalise when truly overbought (>75).
    """
    if 30 <= rsi <= 45:
        return 25.0, f"RSI {rsi:.1f} in recovery zone"
    if 45 < rsi <= 65:
        return 20.0, f"RSI {rsi:.1f} healthy momentum"
    if 65 < rsi <= 75:
        return 10.0, f"RSI {rsi:.1f} strong but not overbought"
    if rsi < 30:
        return 10.0, f"RSI {rsi:.1f} oversold"
    return 0.0, ""


def _score_sma20(close: float, sma20: float) -> tuple[float, str]:
    pct = (close - sma20) / sma20
    if 0 <= pct <= 0.03:
        return 20.0, "Price just above SMA20 (tight)"
    if pct > 0.03:
        return 8.0, "Price above SMA20"
    if -0.02 <= pct < 0:
        return 5.0, "Price near SMA20 (support test)"
    return 0.0, ""


def _score_trend(sma20: float, sma50: float) -> tuple[float, str]:
    if sma20 > sma50:
        return 15.0, "SMA20 > SMA50 (uptrend)"
    if sma20 > sma50 * 0.98:
        return 5.0, "SMA20 near SMA50"
    return 0.0, ""


def _score_volume_stock(vol_ratio: float) -> tuple[float, str]:
    if vol_ratio >= 2.0:
        return 15.0, f"Volume spike {vol_ratio:.1f}x average"
    if vol_ratio >= 1.5:
        return 10.0, f"Volume elevated {vol_ratio:.1f}x"
    if vol_ratio >= 1.2:
        return 5.0, "Volume slightly above average"
    return 0.0, ""


def _score_volume_etf(vol_ratio: float) -> tuple[float, str]:
    # ETFs rarely produce volume spikes — reward consistent participation instead.
    if vol_ratio >= 1.3:
        return 15.0, f"ETF volume active {vol_ratio:.1f}x average"
    if vol_ratio >= 1.0:
        return 10.0, f"ETF volume normal ({vol_ratio:.1f}x)"
    if vol_ratio >= 0.7:
        return 5.0, f"ETF volume below average ({vol_ratio:.1f}x)"
    return 0.0, ""


def _score_atr_stock(atr_val: float, close: float) -> tuple[float, str]:
    atr_pct = atr_val / close if close > 0 else 0
    if 0.01 <= atr_pct <= 0.04:
        return 15.0, f"ATR {atr_pct*100:.1f}% (healthy range)"
    if atr_pct < 0.01:
        return 3.0, "ATR very low (low volatility)"
    return 0.0, ""


def _score_atr_etf(atr_val: float, close: float) -> tuple[float, str]:
    # LSE ETFs typically trade with ATR 0.3–1.5% of price — that is healthy.
    atr_pct = atr_val / close if close > 0 else 0
    if 0.003 <= atr_pct <= 0.02:
        return 15.0, f"ETF ATR {atr_pct*100:.2f}% (healthy for ETF)"
    if 0.001 <= atr_pct < 0.003:
        return 8.0, f"ETF ATR {atr_pct*100:.2f}% (low but acceptable)"
    if atr_pct > 0.02:
        return 5.0, f"ETF ATR {atr_pct*100:.2f}% (elevated)"
    return 0.0, ""


def score_candidate(ticker: str, is_etf: Optional[bool] = None) -> Optional[ScoredCandidate]:
    """
    Fetch market data and compute a signal score for ticker.
    Returns None if data is unavailable or indicators cannot be computed.

    is_etf: pass True/False to force mode; None auto-detects via _ETF_TICKERS.
    """
    data = get_ohlcv(ticker)
    if data is None:
        return None

    df = compute_all(data.df)
    latest = df.iloc[-1]

    for col in ["SMA20", "SMA50", "RSI14", "ATR14"]:
        if pd.isna(latest[col]):
            return None

    close = float(latest["Close"])
    sma20 = float(latest["SMA20"])
    sma50 = float(latest["SMA50"])
    current_rsi = float(latest["RSI14"])
    atr_val = float(latest["ATR14"])
    vol_ratio = float(latest["VolumeRatio"])

    etf_mode = is_etf if is_etf is not None else ticker.upper() in _ETF_TICKERS

    score = 0.0
    reasons: list[str] = []

    for pts, label in [
        (_score_rsi_etf if etf_mode else _score_rsi)(current_rsi),
        _score_sma20(close, sma20),
        _score_trend(sma20, sma50),
        (_score_volume_etf if etf_mode else _score_volume_stock)(vol_ratio),
        (_score_atr_etf if etf_mode else _score_atr_stock)(atr_val, close),
    ]:
        if pts:
            score += pts
            reasons.append(label)

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
