"""
Mission-intent helpers for scan candidate filtering.
"""
from typing import Optional


_ETF_KEYWORDS = [
    "etf",
    "exchange traded fund",
    "exchange-traded fund",
    "index fund",
    "fund",
    "diversified etf",
    "safer etf",
]

_LOWER_RISK_KEYWORDS = [
    "safer",
    "safe",
    "lower risk",
    "low risk",
    "conservative",
    "broad market",
    "diversified",
    "less risky",
    "stable",
]

# Lightweight ETF category map for mission-aware ranking.
# Used only for prioritisation — T212 validation is the authoritative gate.
_ETF_CATEGORIES: dict[str, str] = {
    "VUSA":  "broad_market",
    "VUAG":  "broad_market",
    "CSP1":  "broad_market",
    "VWRP":  "global_equity",
    "SWDA":  "global_equity",
    "IITU":  "technology",
    "EQQQ":  "technology",
    "CNDX":  "technology",
    "VHYL":  "income",
    "INRG":  "clean_energy",
}


def mission_requests_etf(mission: Optional[str]) -> bool:
    """Return True when the mission text explicitly asks for an ETF/fund."""
    if not mission:
        return False
    m = mission.lower()
    return any(kw in m for kw in _ETF_KEYWORDS)


def mission_requests_lower_risk(mission: Optional[str]) -> bool:
    """Return True when the mission signals a preference for lower-risk instruments."""
    if not mission:
        return False
    m = mission.lower()
    return any(kw in m for kw in _LOWER_RISK_KEYWORDS)


def etf_category_for_ticker(ticker: str) -> Optional[str]:
    """Return the broad category for a known ETF ticker, or None."""
    return _ETF_CATEGORIES.get(ticker.upper())
