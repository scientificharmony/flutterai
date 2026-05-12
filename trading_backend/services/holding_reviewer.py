"""
Holding reviewer service.

For each open position, fetches the current price, updates the peak price,
and evaluates whether a sell trigger has been hit. Returns a SellSignal if
any trigger fires, otherwise returns None.

Sell triggers:
  profit_target  — gain >= SELL_TARGET_PCT
  stop_loss      — loss >= STOP_LOSS_PCT
  overbought     — RSI > 75 AND current gain > 0 (don't fire into a loss)
  stale          — position open > STALE_POSITION_DAYS with gain < 1%

No trades are placed. The caller creates the REVIEW_SELL alert and push.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from config import settings
from services.market_data import get_ohlcv

logger = logging.getLogger(__name__)


@dataclass
class SellSignal:
    trigger: str          # profit_target | stop_loss | overbought | stale
    title: str            # push notification title
    body: str             # push notification body
    current_price: float
    gain_pct: float


def evaluate_position(
    ticker: str,
    entry_price: float,
    amount: float,
    peak_price: float | None,
    opened_at: datetime,
) -> tuple[SellSignal | None, float | None]:
    """
    Returns (SellSignal or None, new_peak_price).
    Caller should always update peak_price in the DB with the returned value.
    """
    ohlcv = get_ohlcv(ticker)
    if ohlcv is None:
        logger.warning("Holding review: could not fetch %s", ticker)
        return None, peak_price

    current_price = ohlcv.current_price
    if current_price <= 0 or entry_price <= 0:
        return None, peak_price

    gain_pct = (current_price - entry_price) / entry_price * 100
    new_peak = max(peak_price or current_price, current_price)

    # ── Profit target ────────────────────────────────────────────────────────
    if gain_pct >= settings.sell_target_pct:
        gain_gbp = amount * gain_pct / 100
        return SellSignal(
            trigger="profit_target",
            title=f"{ticker} is up {gain_pct:.1f}% — consider taking profit",
            body=f"Your position is up ~£{gain_gbp:.0f}. Tap to review.",
            current_price=current_price,
            gain_pct=gain_pct,
        ), new_peak

    # ── Stop loss ────────────────────────────────────────────────────────────
    if gain_pct <= -settings.stop_loss_pct:
        loss_gbp = abs(amount * gain_pct / 100)
        return SellSignal(
            trigger="stop_loss",
            title=f"{ticker} is down {abs(gain_pct):.1f}% — consider cutting your loss",
            body=f"Your position is down ~£{loss_gbp:.0f}. Tap to review.",
            current_price=current_price,
            gain_pct=gain_pct,
        ), new_peak

    # ── Overbought (RSI > 75 and in profit) ──────────────────────────────────
    rsi = _calc_rsi(ohlcv.df)
    if rsi is not None and rsi > 75 and gain_pct > 0:
        return SellSignal(
            trigger="overbought",
            title=f"{ticker} looks overbought — good time to review",
            body=f"RSI is {rsi:.0f} and you're up {gain_pct:.1f}%. Tap to check.",
            current_price=current_price,
            gain_pct=gain_pct,
        ), new_peak

    # ── Stale position ───────────────────────────────────────────────────────
    opened_utc = opened_at if opened_at.tzinfo else opened_at.replace(tzinfo=timezone.utc)
    days_open = (datetime.now(timezone.utc) - opened_utc).days
    if days_open >= settings.stale_position_days and abs(gain_pct) < 1.0:
        return SellSignal(
            trigger="stale",
            title=f"{ticker} has barely moved in {days_open} days",
            body="Consider whether to keep holding or free up the capital.",
            current_price=current_price,
            gain_pct=gain_pct,
        ), new_peak

    return None, new_peak


def _calc_rsi(df: pd.DataFrame, period: int = 14) -> float | None:
    try:
        close = df["Close"].dropna()
        if len(close) < period + 1:
            return None
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, float("inf"))
        rsi = 100 - (100 / (1 + rs))
        val = float(rsi.iloc[-1])
        return None if pd.isna(val) else val
    except Exception:
        return None
