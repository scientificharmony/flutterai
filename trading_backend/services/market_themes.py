"""
Market theme universe.
Maps each theme to candidate ETFs/stocks available on T212 UK Invest.
ETF_FIRST_MODE: ETFs are prioritised over individual stocks.
"""
from dataclasses import dataclass, field

ETF_FIRST_MODE = True

# Goal → ordered list of preferred themes
GOAL_THEMES: dict[str, list[str]] = {
    "safer_core":        ["global_equity", "sp500", "defensive", "uk_large_cap"],
    "balanced_growth":   ["global_equity", "sp500", "technology", "healthcare", "dividend_income"],
    "ai_technology":     ["technology", "semiconductors", "sp500", "global_equity"],
    "clean_energy":      ["clean_energy", "technology", "global_equity"],
    "dividend_income":   ["dividend_income", "defensive", "uk_large_cap", "global_equity"],
    "custom":            [],  # Uses preferred_themes from request
}


@dataclass
class ThemeUniverse:
    name: str
    description: str
    etfs: list[str]       # preferred — validated first
    stocks: list[str]     # fallback if ETFs unavailable or high-risk mode


# T212-UK-accessible tickers (verified against common T212 Invest listings)
THEMES: dict[str, ThemeUniverse] = {
    "global_equity": ThemeUniverse(
        name="Global Equity",
        description="Broad global market exposure across developed markets",
        etfs=["VWRP", "IWDA", "SWRD", "HMWO", "VEVE"],
        stocks=["AAPL", "MSFT", "AMZN"],
    ),
    "sp500": ThemeUniverse(
        name="S&P 500",
        description="US large-cap index tracking the top 500 American companies",
        etfs=["VUSA", "CSPX", "IUSA", "VUSD", "SPXP"],
        stocks=["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"],
    ),
    "technology": ThemeUniverse(
        name="Technology",
        description="Global technology sector including software, hardware and internet",
        etfs=["IITU", "XTEC", "EQQQ", "CNDX", "WTEC"],
        stocks=["AAPL", "MSFT", "NVDA", "META", "GOOGL"],
    ),
    "semiconductors": ThemeUniverse(
        name="Semiconductors",
        description="Semiconductor design and manufacturing",
        etfs=["SEMI", "ESEM"],
        stocks=["NVDA", "AMD", "ASML", "INTC", "TSM"],
    ),
    "healthcare": ThemeUniverse(
        name="Healthcare",
        description="Global healthcare, pharmaceuticals and biotech",
        etfs=["IUHC", "XDWH", "WHCS"],
        stocks=["JNJ", "UNH", "PFE", "ABBV", "MRK"],
    ),
    "dividend_income": ThemeUniverse(
        name="Dividend Income",
        description="High-yield dividend stocks and ETFs for regular income",
        etfs=["VHYL", "TDIV", "HDIV", "IDVY"],
        stocks=["JNJ", "KO", "PG", "VZ", "T"],
    ),
    "clean_energy": ThemeUniverse(
        name="Clean Energy",
        description="Renewable energy, solar, wind and energy transition",
        etfs=["INRG", "RENE", "IGEN"],
        stocks=["ENPH", "SEDG", "NEE", "BEP", "ORSTED"],
    ),
    "uk_large_cap": ThemeUniverse(
        name="UK Large Cap",
        description="FTSE 100 and UK blue-chip equities",
        etfs=["ISF", "VUKE", "VMID", "CUKX"],
        stocks=["SHEL", "AZN", "HSBA", "BATS", "BP"],
    ),
    "defensive": ThemeUniverse(
        name="Defensive",
        description="Low-volatility, consumer staples, gold and safe-haven assets",
        etfs=["IGLN", "XDWI", "MVOL", "IEFM"],
        stocks=["KO", "PG", "WMT", "COST", "JNJ"],
    ),
}


def get_candidates_for_themes(
    themes: list[str],
    etf_first: bool = ETF_FIRST_MODE,
) -> list[tuple[str, str]]:
    """
    Return ordered list of (ticker, theme) pairs for the given themes.
    ETFs come before stocks when etf_first=True.
    """
    seen: set[str] = set()
    result: list[tuple[str, str]] = []

    for theme_key in themes:
        universe = THEMES.get(theme_key)
        if not universe:
            continue
        candidates = (universe.etfs + universe.stocks) if etf_first else (universe.stocks + universe.etfs)
        for ticker in candidates:
            if ticker not in seen:
                seen.add(ticker)
                result.append((ticker, theme_key))

    return result


def themes_for_goal(goal: str, preferred: list[str], excluded: list[str]) -> list[str]:
    """
    Return the ordered theme list for a goal, merging preferred overrides
    and removing excluded themes.
    """
    base = GOAL_THEMES.get(goal, [])
    # Prepend preferred if not already present
    merged = list(preferred) + [t for t in base if t not in preferred]
    return [t for t in merged if t not in excluded]
