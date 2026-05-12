"""
Pie opportunity scoring engine.
Scores each candidate 0–100 across five dimensions.
Only candidates with opportunity_score >= 70 pass to the allocation engine.
"""
import logging
from typing import Optional

import pandas as pd

from services.market_data import get_ohlcv
from services.indicators import sma, rsi, atr, volume_ratio, compute_all
from models.pie_schemas import ScoredPieCandidate

logger = logging.getLogger(__name__)

MIN_OPPORTUNITY_SCORE = 70.0
MIN_DATA_ROWS = 60  # Need at least 60 trading days for reliable indicators


def _trend_score(df: pd.DataFrame) -> float:
    """
    Long-term trend health (0–25).
    Rewards price above SMA50 and SMA200 alignment.
    """
    close = df["Close"].iloc[-1]
    sma50 = sma(df["Close"], 50).iloc[-1]
    sma200_series = sma(df["Close"], 200)
    sma200 = sma200_series.iloc[-1] if not pd.isna(sma200_series.iloc[-1]) else sma50

    score = 0.0
    if close > sma50:
        score += 12
    if sma50 > sma200:
        score += 8
    # Tight range between price and SMA50 suggests stable trend
    gap = abs(close - sma50) / sma50
    if gap <= 0.05:
        score += 5
    elif gap <= 0.10:
        score += 2
    return min(score, 25.0)


def _momentum_score(df: pd.DataFrame) -> float:
    """
    Momentum quality (0–25).
    RSI sweet spot + 3-month return vs 1-month return (improving momentum).
    """
    rsi14 = rsi(df["Close"], 14).iloc[-1]
    if pd.isna(rsi14):
        return 0.0

    score = 0.0
    if 45 <= rsi14 <= 65:
        score += 15  # Healthy momentum zone
    elif 35 <= rsi14 < 45:
        score += 10  # Recovery zone
    elif 65 < rsi14 <= 75:
        score += 8   # Strong but not overbought
    elif rsi14 > 75:
        score += 2   # Overbought — penalise

    # 3-month vs 1-month return comparison
    if len(df) >= 63:
        ret_3m = (df["Close"].iloc[-1] / df["Close"].iloc[-63] - 1) * 100
        ret_1m = (df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) * 100 if len(df) >= 21 else 0
        if ret_3m > 0 and ret_1m > 0:
            score += 7
        elif ret_3m > 0:
            score += 4
        elif ret_3m < -10:
            score -= 5

    return max(0.0, min(score, 25.0))


def _volume_score(df: pd.DataFrame) -> float:
    """
    Volume consistency (0–20).
    Rewards stable, gradually increasing volume — penalises erratic spikes.
    """
    vol = df["Volume"]
    vol_ratio_val = volume_ratio(vol, 20)

    score = 0.0
    if 0.8 <= vol_ratio_val <= 1.5:
        score += 15  # Healthy consistent volume
    elif 1.5 < vol_ratio_val <= 2.5:
        score += 10  # Elevated but manageable
    elif vol_ratio_val > 2.5:
        score += 5   # Spike — could be news-driven
    elif vol_ratio_val < 0.5:
        score += 2   # Very low liquidity

    # Reward liquid instruments (high avg volume)
    avg_vol = float(vol.rolling(20).mean().iloc[-1])
    if avg_vol > 5_000_000:
        score += 5
    elif avg_vol > 1_000_000:
        score += 3
    elif avg_vol > 100_000:
        score += 1

    return min(score, 20.0)


def _volatility_score(df: pd.DataFrame) -> float:
    """
    Volatility suitability (0–15).
    For Pie Builder, lower volatility is preferred — rewards stability.
    """
    close = df["Close"].iloc[-1]
    atr14 = atr(df["High"], df["Low"], df["Close"], 14).iloc[-1]
    if pd.isna(atr14) or close == 0:
        return 0.0

    atr_pct = atr14 / close

    if atr_pct <= 0.01:
        return 15.0   # Very stable (typical ETF)
    elif atr_pct <= 0.02:
        return 12.0
    elif atr_pct <= 0.03:
        return 8.0
    elif atr_pct <= 0.05:
        return 4.0
    else:
        return 1.0    # Too volatile for a conservative Pie


def _diversification_score(theme: str, already_selected_themes: list[str]) -> float:
    """
    Diversification bonus (0–15).
    New themes get full score; repeated themes lose points.
    """
    count = already_selected_themes.count(theme)
    if count == 0:
        return 15.0
    elif count == 1:
        return 8.0
    else:
        return 2.0


def score_pie_candidate(
    ticker: str,
    theme: str,
    instrument_type: str,
    already_selected_themes: list[str],
) -> Optional[ScoredPieCandidate]:
    """
    Score a single candidate for Pie inclusion.
    Returns None if data is unavailable or stale.
    """
    data = get_ohlcv(ticker, period="1y")
    if data is None or len(data.df) < MIN_DATA_ROWS:
        logger.debug("Skipping %s: insufficient data (%s rows)", ticker, len(data.df) if data else 0)
        return None

    df = data.df

    try:
        t = _trend_score(df)
        m = _momentum_score(df)
        v = _volume_score(df)
        vl = _volatility_score(df)
        d = _diversification_score(theme, already_selected_themes)
    except Exception as exc:
        logger.warning("Scoring failed for %s: %s", ticker, exc)
        return None

    opportunity_score = round(t + m + v + vl + d, 2)

    return ScoredPieCandidate(
        ticker=ticker,
        name=ticker,  # Overwritten by T212 instrument name in router
        instrument_type=instrument_type,  # type: ignore[arg-type]
        market_theme=theme,
        opportunity_score=opportunity_score,
        trend_score=round(t, 2),
        momentum_score=round(m, 2),
        volume_score=round(v, 2),
        volatility_score=round(vl, 2),
        diversification_score=round(d, 2),
        current_price=data.current_price,
        data_timestamp=data.data_timestamp,
    )
