from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

ACTION_STRENGTH_DISCLAIMER = (
    "Action Strength ranks how strongly this setup matches your rules. "
    "It is not a guarantee or probability of profit."
)


def label_for_action_strength(score: int) -> str:
    if score <= 29:
        return "Ignore"
    if score <= 49:
        return "Watch Only"
    if score <= 69:
        return "Review"
    if score <= 84:
        return "Strong Review"
    return "High-Priority Review"


def interpretation_for_score(score: int) -> str:
    label = label_for_action_strength(score)
    return f"Action Strength {score}/100: {label}."


# ── Requests ──────────────────────────────────────────────────────────────────

class ManualScanRequest(BaseModel):
    mission: str
    watchlist: list[str] = Field(default_factory=list)

class HoldingReviewRequest(BaseModel):
    ticker: str
    currently_owned: bool
    holding_loss_pct: float = Field(default=0, ge=0, le=100)
    holding_weight_pct: float = Field(default=0, ge=0, le=100)
    sector_concentration_pct: float = Field(default=0, ge=0, le=100)
    mission: Optional[str] = None


class RegisterTokenRequest(BaseModel):
    token: str
    platform: Literal["ios", "android"]


# ── Claude response (internal) ────────────────────────────────────────────────

class ClaudeRecommendation(BaseModel):
    ticker: str
    claude_confidence: int = Field(ge=0, le=100)
    reasoning_quality: int = Field(ge=0, le=100)
    key_factors: list[str]
    risks: list[str]
    contradiction_notes: list[str] = Field(default_factory=list)
    plain_english_summary: str

ClaudeRecommendationAnalysis = ClaudeRecommendation

class RecommendationScore(BaseModel):
    formula_score: int = Field(ge=0, le=100)
    claude_confidence: int = Field(ge=0, le=100)
    portfolio_fit_score: Optional[int] = Field(default=None, ge=0, le=100)
    weakness_score: Optional[int] = Field(default=None, ge=0, le=100)
    drawdown_risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    exposure_risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action_strength: int = Field(ge=0, le=100)
    action_label: str
    score_interpretation: str
    action_strength_disclaimer: str = ACTION_STRENGTH_DISCLAIMER

# ── API responses ─────────────────────────────────────────────────────────────

class TradeAlertResponse(BaseModel):
    id: str
    ticker: str
    action: str
    signal_score: float
    confidence: int
    formula_score: int = Field(ge=0, le=100)
    claude_confidence: int = Field(ge=0, le=100)
    portfolio_fit_score: Optional[int] = Field(default=None, ge=0, le=100)
    weakness_score: Optional[int] = Field(default=None, ge=0, le=100)
    drawdown_risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    exposure_risk_score: Optional[int] = Field(default=None, ge=0, le=100)
    action_strength: int = Field(ge=0, le=100)
    action_label: str
    score_interpretation: str
    action_strength_disclaimer: str = ACTION_STRENGTH_DISCLAIMER
    trading212_review_enabled: bool
    t212_ticker: Optional[str] = None  # full T212 canonical ticker e.g. VHYLL_EQ
    t212_review_url: Optional[str] = None  # direct URL to instrument in T212
    suggested_amount: float
    price_at_alert: float
    alert_title: str
    alert_body: str
    rationale: str
    risk_note: str
    key_factors: list[str]
    blocking_risks: list[str]
    expires_at: datetime
    executable: bool
    safety_flags: list[str]
    created_at: datetime


class ScanResponse(BaseModel):
    status: str
    user_balance: float
    max_trade_amount: float
    alert: Optional[TradeAlertResponse] = None
    message: Optional[str] = None
    budget_reached: bool = False
    safety_flags: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    claude_configured: bool
    trading212_configured: bool
    mode: str


class StrategyPerformanceRow(BaseModel):
    ticker: str
    action: str
    signal_score: float
    confidence: int
    suggested_amount: float
    price_at_alert: float
    price_1h: Optional[float]
    price_4h: Optional[float]
    price_1d: Optional[float]
    price_5d: Optional[float]
    max_gain: Optional[float]
    max_drawdown: Optional[float]
    created_at: datetime


# ── Trade outcome recording ───────────────────────────────────────────────────

class RecordOutcomeRequest(BaseModel):
    outcome: Literal["took_trade", "ignored", "watching"]
    manual_entry_price: Optional[float] = None
    manual_amount: Optional[float] = None
    trade_notes: Optional[str] = None


class CloseTradeRequest(BaseModel):
    manual_exit_price: float
    realised_pnl: Optional[float] = None
    trade_notes: Optional[str] = None


class SignalPerformanceResponse(BaseModel):
    alert_id: str
    ticker: str
    action: str
    formula_score: float
    claude_confidence: int
    action_strength: int = Field(ge=0, le=100)
    action_label: str
    price_at_alert: float
    suggested_amount: float
    outcome: Optional[str]
    manual_entry_price: Optional[float]
    manual_exit_price: Optional[float]
    manual_amount: Optional[float]
    realised_pnl: Optional[float]
    trade_notes: Optional[str]
    price_1h: Optional[float]
    price_4h: Optional[float]
    price_1d: Optional[float]
    price_5d: Optional[float]
    max_gain_1d: Optional[float]
    max_drawdown_1d: Optional[float]
    claude_cost_estimate: float
    created_at: datetime


# ── Private dashboard ─────────────────────────────────────────────────────────

class DailyUsageSummary(BaseModel):
    date: str
    claude_calls: int
    estimated_cost_gbp: float
    market_data_calls: int
    alerts_sent: int
    budget_remaining_gbp: float


class PerformanceSummary(BaseModel):
    total_alerts: int
    took_trade: int
    ignored: int
    watching: int
    unrecorded: int
    win_rate_pct: Optional[float]
    avg_1d_pct: Optional[float]
    avg_5d_pct: Optional[float]
    total_realised_pnl: float
    estimated_claude_cost_gbp: float
    estimated_market_data_cost_gbp: float
    net_after_api_costs: float
    average_1h_result: Optional[float]
    average_4h_result: Optional[float]
    average_1d_result: Optional[float]
    average_5d_result: Optional[float]
    acted_on_result: Optional[float]
    ignored_result: Optional[float]
    api_cost_per_band: dict[str, float]
    best_performing_action_strength_band: Optional[str]
    worst_performing_action_strength_band: Optional[str]
    today_usage: DailyUsageSummary
    recent_signals: list[SignalPerformanceResponse]
