from services.trading212_service import get_t212_ticker


def test_get_t212_ticker_normalises_to_uppercase():
    # Simulate a cached instrument entry with non-normalised casing.
    from services import trading212_service
    trading212_service._instruments_cache = {
        "VHYLL": {"ticker": "VHYLl_EQ", "tradable": True, "type": "ETF"}
    }
    assert get_t212_ticker("VHYLL") == "VHYLL_EQ"

