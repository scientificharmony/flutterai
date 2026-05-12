"""
Pure-function technical indicators.
All functions accept a pandas Series or DataFrame and return a Series or scalar.
"""
import pandas as pd
import numpy as np


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


def volume_ratio(volume: pd.Series, period: int = 20) -> float:
    avg = volume.rolling(window=period, min_periods=period).mean().iloc[-1]
    if avg == 0 or pd.isna(avg):
        return 1.0
    return float(volume.iloc[-1] / avg)


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Attach SMA20, SMA50, RSI14, ATR14, VolumeRatio columns to df."""
    df = df.copy()
    df["SMA20"] = sma(df["Close"], 20)
    df["SMA50"] = sma(df["Close"], 50)
    df["RSI14"] = rsi(df["Close"], 14)
    df["ATR14"] = atr(df["High"], df["Low"], df["Close"], 14)
    df["VolumeRatio"] = volume_ratio(df["Volume"], 20)
    return df
