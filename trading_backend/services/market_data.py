import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

# Simple in-memory cache: ticker → (fetch_unix_ts, DataFrame)
_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# LSE-listed ETFs that Yahoo Finance requires a .L suffix for.
# Keyed by the bare ticker used everywhere else in the app.
_LSE_TICKERS: set[str] = {
    "VUSA", "VUAG", "VWRP", "IITU", "EQQQ",
    "INRG", "SWDA", "CSP1", "CNDX", "ISF", "VEVE",
}

# T212 tickers whose Yahoo Finance symbol differs from ticker + ".L".
# Takes priority over _LSE_TICKERS.
_YF_OVERRIDES: dict[str, str] = {
    "VHYLL": "VHYL.L",  # T212 VHYLL_EQ → Yahoo VHYL.L (LSE distributing)
    "VHYLA": "VHYL.L",  # T212 VHYLA_EQ → same underlying fund on Yahoo
}


def _yf_ticker(ticker: str) -> str:
    """Return the Yahoo Finance symbol for a ticker."""
    upper = ticker.upper()
    if upper in _YF_OVERRIDES:
        return _YF_OVERRIDES[upper]
    return f"{upper}.L" if upper in _LSE_TICKERS else upper


@dataclass
class OHLCVData:
    ticker: str
    df: pd.DataFrame          # columns: Open, High, Low, Close, Volume
    current_price: float
    current_volume: float
    data_timestamp: datetime  # UTC datetime of the newest row in df


def _is_fresh(ticker: str) -> bool:
    if ticker not in _cache:
        return False
    ts, _ = _cache[ticker]
    return (time.time() - ts) < _CACHE_TTL_SECONDS


def _newest_row_timestamp(df: pd.DataFrame) -> datetime:
    """Return the index datetime of the last row, normalised to UTC."""
    idx = df.index[-1]
    if hasattr(idx, "tzinfo") and idx.tzinfo is not None:
        return idx.to_pydatetime().astimezone(timezone.utc).replace(tzinfo=None)
    # yfinance date-only index — treat as end-of-day UTC
    return pd.Timestamp(idx).to_pydatetime().replace(tzinfo=None)


def get_ohlcv(ticker: str, period: str = "3mo") -> Optional[OHLCVData]:
    """Fetch OHLCV data for a ticker. Returns None if unavailable."""
    if not _is_fresh(ticker):
        try:
            raw = yf.download(_yf_ticker(ticker), period=period, progress=False, auto_adjust=True)
            if raw.empty or len(raw) < 50:
                return None
            # Flatten MultiIndex columns if present (yfinance ≥0.2.x)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            _cache[ticker] = (time.time(), raw)
        except Exception:
            return None

    _, df = _cache[ticker]
    if df.empty:
        return None

    return OHLCVData(
        ticker=ticker,
        df=df.copy(),
        current_price=float(df["Close"].iloc[-1]),
        current_volume=float(df["Volume"].iloc[-1]),
        data_timestamp=_newest_row_timestamp(df),
    )


def get_current_price(ticker: str) -> Optional[float]:
    data = get_ohlcv(ticker)
    return data.current_price if data else None


def get_data_timestamp(ticker: str) -> Optional[datetime]:
    data = get_ohlcv(ticker)
    return data.data_timestamp if data else None


def invalidate(ticker: str) -> None:
    _cache.pop(ticker, None)
