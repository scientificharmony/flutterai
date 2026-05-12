import pytest
from services.mission_filters import (
    etf_category_for_ticker,
    mission_requests_etf,
    mission_requests_lower_risk,
)


# ── mission_requests_etf ──────────────────────────────────────────────────────

@pytest.mark.parametrize("mission", [
    "Find a safer ETF opportunity",
    "I want an ETF",
    "find me an exchange traded fund",
    "exchange-traded fund please",
    "looking for an index fund",
    "give me a fund",
    "diversified etf please",
    "safer etf option",
    "Find a SAFER ETF OPPORTUNITY",   # case insensitive
])
def test_mission_requests_etf_returns_true(mission):
    assert mission_requests_etf(mission) is True


@pytest.mark.parametrize("mission", [
    "Find a technology stock",
    "NVDA momentum play",
    "I want AAPL",
    None,
    "",
    "Buy high sell low",
])
def test_mission_requests_etf_returns_false(mission):
    assert mission_requests_etf(mission) is False


# ── mission_requests_lower_risk ───────────────────────────────────────────────

@pytest.mark.parametrize("mission", [
    "Find a safer ETF opportunity",
    "I want something safe",
    "lower risk please",
    "low risk investment",
    "conservative approach",
    "broad market exposure",
    "diversified portfolio",
    "less risky option",
    "stable returns",
    "SAFER OPTION",   # case insensitive
])
def test_mission_requests_lower_risk_returns_true(mission):
    assert mission_requests_lower_risk(mission) is True


@pytest.mark.parametrize("mission", [
    "Find a momentum technology play",
    "aggressive growth",
    "high risk high reward",
    None,
    "",
    "NVDA semiconductor",
])
def test_mission_requests_lower_risk_returns_false(mission):
    assert mission_requests_lower_risk(mission) is False


# ── etf_category_for_ticker ───────────────────────────────────────────────────

@pytest.mark.parametrize("ticker,expected_category", [
    ("VUSA",  "broad_market"),
    ("VUAG",  "broad_market"),
    ("CSP1",  "broad_market"),
    ("VWRP",  "global_equity"),
    ("SWDA",  "global_equity"),
    ("IITU",  "technology"),
    ("EQQQ",  "technology"),
    ("CNDX",  "technology"),
    ("VHYLL", "income"),
    ("VHYLA", "income"),
    ("INRG",  "clean_energy"),
    ("vusa",  "broad_market"),   # lowercase normalised
])
def test_etf_category_for_ticker_known(ticker, expected_category):
    assert etf_category_for_ticker(ticker) == expected_category


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "NVDA", "UNKNOWN", ""])
def test_etf_category_for_ticker_unknown_returns_none(ticker):
    assert etf_category_for_ticker(ticker) is None
