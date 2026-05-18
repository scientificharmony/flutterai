import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _uid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uid, primary_key=True)
    device_id: str = Field(unique=True, index=True)
    plan: str = Field(default="free")  # free | pro
    created_at: datetime = Field(default_factory=_utcnow)


class UserSettings(SQLModel, table=True):
    __tablename__ = "user_settings"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    quiet_hours_start: int = Field(default=22)
    quiet_hours_end: int = Field(default=8)
    max_risk_pct: float = Field(default=10.0)
    notifications_enabled: bool = Field(default=True)


class Strategy(SQLModel, table=True):
    __tablename__ = "strategies"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    name: str
    watchlist: list = Field(default_factory=list, sa_column=Column(JSON))
    min_confidence: int = Field(default=70)
    min_signal_score: float = Field(default=75.0)
    enabled: bool = Field(default=True)
    scan_interval_minutes: int = Field(default=60)
    last_scanned_at: Optional[datetime] = None


class TradeAlert(SQLModel, table=True):
    __tablename__ = "trade_alerts"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    strategy_id: Optional[str] = Field(foreign_key="strategies.id", default=None)
    ticker: str = Field(index=True)
    action: str  # BUY_REVIEW | REVIEW_SELL | HOLD | WATCH | DO_NOT_ACT
    signal_score: float
    confidence: int
    formula_score: int = Field(default=0)
    claude_confidence: int = Field(default=50)
    portfolio_fit_score: Optional[int] = None
    weakness_score: Optional[int] = None
    drawdown_risk_score: Optional[int] = None
    exposure_risk_score: Optional[int] = None
    action_strength: int = Field(default=0)
    action_label: str = Field(default="Ignore")
    score_interpretation: str = Field(default="")
    action_strength_disclaimer: str = Field(default="")
    suggested_amount: float
    price_at_alert: float
    alert_title: str
    alert_body: str
    what_is_this: str = Field(default="")
    rationale: str
    risk_note: str
    key_factors: list = Field(default_factory=list, sa_column=Column(JSON))
    blocking_risks: list = Field(default_factory=list, sa_column=Column(JSON))
    expires_at: datetime
    executable: bool = Field(default=False)
    safety_flags: list = Field(default_factory=list, sa_column=Column(JSON))
    push_sent: bool = Field(default=False)
    sell_trigger: Optional[str] = None  # profit_target | stop_loss | overbought | stale
    created_at: datetime = Field(default_factory=_utcnow)


class ScanUsage(SQLModel, table=True):
    __tablename__ = "scan_usage"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    date: str = Field(index=True)  # YYYY-MM-DD
    scan_count: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)


class AlertOutcome(SQLModel, table=True):
    __tablename__ = "alert_outcomes"

    id: str = Field(default_factory=_uid, primary_key=True)
    alert_id: str = Field(foreign_key="trade_alerts.id", unique=True, index=True)
    price_1h: Optional[float] = None
    price_4h: Optional[float] = None
    price_1d: Optional[float] = None
    price_5d: Optional[float] = None
    max_gain: Optional[float] = None
    max_drawdown: Optional[float] = None
    measured_at: Optional[datetime] = None


class DeviceToken(SQLModel, table=True):
    __tablename__ = "device_tokens"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    token: str = Field(unique=True)
    platform: str  # ios | android
    created_at: datetime = Field(default_factory=_utcnow)


# ── Private test mode tables ──────────────────────────────────────────────────

class DailyAiUsage(SQLModel, table=True):
    __tablename__ = "daily_ai_usage"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(index=True)
    date: str = Field(index=True)  # YYYY-MM-DD
    claude_calls: int = Field(default=0)
    estimated_cost_gbp: float = Field(default=0.0)
    market_data_calls: int = Field(default=0)
    alerts_sent: int = Field(default=0)


class SignalPerformance(SQLModel, table=True):
    __tablename__ = "signal_performance"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(index=True)
    alert_id: str = Field(foreign_key="trade_alerts.id", unique=True, index=True)
    ticker: str
    strategy: Optional[str] = None
    action: str
    formula_score: float
    claude_confidence: int
    action_strength: int = Field(default=0)
    action_label: str = Field(default="Ignore")
    price_at_alert: float
    suggested_amount: float

    # Manual trade outcome
    outcome: Optional[str] = None  # "took_trade" | "ignored" | "watching"
    manual_entry_price: Optional[float] = None
    manual_exit_price: Optional[float] = None
    manual_amount: Optional[float] = None
    trade_notes: Optional[str] = None
    realised_pnl: Optional[float] = None

    # Price tracking
    price_1h: Optional[float] = None
    price_4h: Optional[float] = None
    price_1d: Optional[float] = None
    price_5d: Optional[float] = None
    max_gain_1d: Optional[float] = None
    max_drawdown_1d: Optional[float] = None

    # Cost tracking
    claude_cost_estimate: float = Field(default=0.002)
    market_data_cost_estimate: float = Field(default=0.0001)

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── Open position tracker ─────────────────────────────────────────────────────

class OpenPosition(SQLModel, table=True):
    __tablename__ = "open_positions"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    signal_perf_id: str = Field(foreign_key="signal_performance.id", unique=True, index=True)
    ticker: str = Field(index=True)
    entry_price: float
    amount: float
    peak_price: Optional[float] = None  # highest price seen since entry
    status: str = Field(default="open")  # open | closed
    sell_alert_id: Optional[str] = None  # set when REVIEW_SELL alert fires
    opened_at: datetime = Field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None


# ── Forex Lab practice positions ──────────────────────────────────────────────

class ForexPosition(SQLModel, table=True):
    __tablename__ = "forex_positions"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    pair: str = Field(index=True)
    direction: str  # LONG | SHORT
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    position_units: int = Field(default=0)
    timeframe: str = Field(default="15m")
    ig_deal_id: Optional[str] = None
    ig_epic: Optional[str] = None
    ig_size: Optional[float] = None
    status: str = Field(default="open")  # open | closed
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None
    last_assistant_status: Optional[str] = None
    last_notified_status: Optional[str] = None
    opened_at: datetime = Field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None


class ForexEntryAlert(SQLModel, table=True):
    __tablename__ = "forex_entry_alerts"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    pair: str = Field(index=True)
    direction: str  # LONG | SHORT
    strength: int
    timeframe: str = Field(default="15m")
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    position_units: int = Field(default=0)
    rationale: str = Field(default="")
    push_sent: bool = Field(default=False)
    declined: bool = Field(default=False)
    declined_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class CfdEntryAlert(SQLModel, table=True):
    __tablename__ = "cfd_entry_alerts"

    id: str = Field(default_factory=_uid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    market: str = Field(index=True)  # e.g. "FTSE 100"
    epic: str = Field(index=True)
    direction: str  # LONG | SHORT
    strength: int
    timeframe: str = Field(default="15m")
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    contract_size: float = Field(default=1.0)
    rationale: str = Field(default="")
    push_sent: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
