from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

# ── Allowed enumerations ──────────────────────────────────────────────────────

RiskLevel = Literal["low", "medium", "high"]

Goal = Literal[
    "safer_core",
    "balanced_growth",
    "ai_technology",
    "clean_energy",
    "dividend_income",
    "custom",
]

AllowedTheme = Literal[
    "global_equity",
    "sp500",
    "technology",
    "semiconductors",
    "healthcare",
    "dividend_income",
    "clean_energy",
    "uk_large_cap",
    "defensive",
]

InstrumentType = Literal["STOCK", "ETF"]

ALLOWED_INSTRUMENT_TYPES: set[str] = {"STOCK", "ETF"}
REJECTED_INSTRUMENT_TYPES: set[str] = {
    "CFD", "FOREX", "CRYPTO", "OPTION", "LEVERAGED", "SHORT", "UNKNOWN"
}

# How old the newest data row can be before we consider it stale (market days)
DATA_STALENESS_DAYS = 3

# Minimum £ per slice for a Pie to be executable
PRACTICAL_MIN_SLICE_AMOUNT = 1.0

# ── Request ───────────────────────────────────────────────────────────────────

class PieBuildRequest(BaseModel):
    goal: Goal
    risk_level: RiskLevel
    total_amount: float = Field(gt=0)
    time_horizon: str = Field(description="e.g. '1 year', '5 years', 'long-term'")
    preferred_themes: list[AllowedTheme] = Field(default_factory=list)
    excluded_themes: list[AllowedTheme] = Field(default_factory=list)


# ── Internal intermediate types ───────────────────────────────────────────────

class ScoredPieCandidate(BaseModel):
    ticker: str
    name: str
    instrument_type: InstrumentType
    market_theme: str
    opportunity_score: float           # 0–100
    trend_score: float
    momentum_score: float
    volume_score: float
    volatility_score: float
    diversification_score: float
    current_price: float
    data_timestamp: datetime           # UTC timestamp of the newest OHLCV row
    invest_validated: bool = True      # passed T212 Invest STOCK/ETF check


# ── Response ──────────────────────────────────────────────────────────────────

class PieSlice(BaseModel):
    ticker: str
    name: str
    instrument_type: InstrumentType
    market_theme: str
    allocation_percent: float          # e.g. 40.0
    amount: float                      # £ amount
    opportunity_score: float
    opportunity_strength: int = Field(ge=0, le=100)
    strength_label: str
    rationale: str


class DataFreshness(BaseModel):
    status: Literal["fresh", "stale", "unavailable"]
    newest_data_timestamp: datetime
    oldest_allowed_timestamp: datetime
    stale_tickers: list[str]


class PieBuildResponse(BaseModel):
    pie_name: str
    goal: str
    risk_level: str
    total_amount: float
    time_horizon: str
    slices: list[PieSlice]
    overall_rationale: str
    risk_note: str
    executable: bool
    safety_flags: list[str]
    warnings: list[str]

    # Freshness / safety fields
    data_freshness: DataFreshness
    market_data_timestamp: datetime    # newest data row across all slices
    valid_until: datetime              # market_data_timestamp + 24h
    invest_only_verified: bool         # all slices passed T212 Invest check
    all_slices_validated: bool         # all slices have ticker + instrument data
    manual_execution_only: bool = True # always True — never automated


# ── Saved Pie response ────────────────────────────────────────────────────────

class SavePieRequest(BaseModel):
    pie: PieBuildResponse


class SavedPieResponse(BaseModel):
    id: str
    pie_name: str
    risk_level: str
    total_amount: float
    created_at: str
    slices: list[PieSlice]


# ── Templates ─────────────────────────────────────────────────────────────────

class PieTemplate(BaseModel):
    id: str
    name: str
    goal: str
    risk_level: str
    description: str
    themes: list[str]
    pro_only: bool
