"""
Shared fixtures for the Pie Builder test suite.

All external calls (T212, yfinance, Claude) are mocked.
The FastAPI TestClient uses SQLite so no Postgres is required.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timedelta, timezone

import pandas as pd
import numpy as np
from unittest.mock import patch

from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool


# ── In-memory SQLite engine ───────────────────────────────────────────────────

@pytest.fixture(name="db_engine", scope="session")
def db_engine_fixture():
    # Import all models so SQLModel.metadata is fully populated
    import models.db_models  # noqa: F401
    import models.pie_schemas  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture(name="client")
def client_fixture(db_engine):
    from fastapi.testclient import TestClient
    from database import get_session

    def _override():
        with Session(db_engine) as s:
            yield s

    # Patch scheduler and DB table creation so no Postgres connection is needed
    with patch("main.start_scheduler"), \
         patch("main.stop_scheduler"), \
         patch("database.create_db_and_tables"):
        from main import app
        app.dependency_overrides[get_session] = _override
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()


# ── Synthetic OHLCV ───────────────────────────────────────────────────────────

def make_ohlcv_data(ticker: str = "VUSA", newest_offset_days: int = 0):
    """Return an OHLCVData whose newest row is `newest_offset_days` before today."""
    from services.market_data import OHLCVData
    end = datetime.now(timezone.utc) - timedelta(days=newest_offset_days)
    dates = pd.date_range(end=end, periods=252, freq="B")
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(252) * 0.5)
    df = pd.DataFrame(
        {
            "Open":   close * 0.99,
            "High":   close * 1.01,
            "Low":    close * 0.98,
            "Close":  close,
            "Volume": np.random.randint(1_000_000, 5_000_000, 252).astype(float),
        },
        index=dates,
    )
    return OHLCVData(
        ticker=ticker,
        df=df,
        current_price=float(df["Close"].iloc[-1]),
        current_volume=float(df["Volume"].iloc[-1]),
        data_timestamp=df.index[-1].to_pydatetime(),
    )


# ── Scored candidate factory ──────────────────────────────────────────────────

def make_candidate(
    ticker: str = "VUSA",
    instrument_type: str = "ETF",
    theme: str = "global_equity",
    score: float = 82.0,
    newest_offset_days: int = 0,
):
    from models.pie_schemas import ScoredPieCandidate
    ts = datetime.now(timezone.utc) - timedelta(days=newest_offset_days)
    return ScoredPieCandidate(
        ticker=ticker,
        name=ticker,
        instrument_type=instrument_type,   # type: ignore[arg-type]
        market_theme=theme,
        opportunity_score=score,
        trend_score=20.0,
        momentum_score=20.0,
        volume_score=15.0,
        volatility_score=15.0,
        diversification_score=score - 70.0,
        current_price=50.0,
        data_timestamp=ts,
        invest_validated=True,
    )
