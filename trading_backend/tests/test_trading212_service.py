import asyncio
from unittest.mock import AsyncMock, patch

from services import trading212_service


def _reset_cache():
    trading212_service._instruments_cache = {}
    trading212_service._instruments_fetched_at = 0.0


def test_validate_invest_instrument_accepts_unique_t212_alias():
    _reset_cache()
    instruments = [
        {
            "ticker": "META_US_EQ",
            "shortName": "META",
            "name": "Meta Platforms Inc",
            "type": "STOCK",
            "tradable": True,
        }
    ]

    with patch("services.trading212_service._fetch_instruments", new=AsyncMock(return_value=instruments)):
        valid, inst_type = asyncio.run(trading212_service.validate_invest_instrument("META"))

    assert valid is True
    assert inst_type == "STOCK"


def test_validate_invest_instrument_rejects_unknown_ticker():
    _reset_cache()

    with patch("services.trading212_service._fetch_instruments", new=AsyncMock(return_value=[])):
        valid, inst_type = asyncio.run(trading212_service.validate_invest_instrument("NOPE"))

    assert valid is False
    assert inst_type == "UNKNOWN"


def test_validate_invest_instrument_rejects_non_invest_type():
    _reset_cache()
    instruments = [
        {
            "ticker": "BTC_GBP",
            "shortName": "BTC",
            "name": "Bitcoin",
            "type": "CRYPTO",
            "tradable": True,
        }
    ]

    with patch("services.trading212_service._fetch_instruments", new=AsyncMock(return_value=instruments)):
        valid, inst_type = asyncio.run(trading212_service.validate_invest_instrument("BTC"))

    assert valid is False
    assert inst_type == "CRYPTO"


def test_validate_invest_instrument_rejects_ambiguous_alias():
    _reset_cache()
    instruments = [
        {"ticker": "ABC_US_EQ", "shortName": "ABC", "type": "STOCK", "tradable": True},
        {"ticker": "ABC_LN_EQ", "shortName": "ABC", "type": "STOCK", "tradable": True},
    ]

    with patch("services.trading212_service._fetch_instruments", new=AsyncMock(return_value=instruments)):
        valid, inst_type = asyncio.run(trading212_service.validate_invest_instrument("ABC"))

    assert valid is False
    assert inst_type == "UNKNOWN"
