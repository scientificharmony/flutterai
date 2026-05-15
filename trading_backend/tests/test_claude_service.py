from services.claude_service import _sanitise_what_is_this


def test_sanitise_what_is_this_strips_other_candidate_tickers():
    valid = {"VHYLL", "HMCH", "ISF"}
    assert _sanitise_what_is_this("HMCH", "VHYLL is a fund that does X.", valid) == ""


def test_sanitise_what_is_this_keeps_clean_sentence():
    valid = {"VHYLL", "HMCH"}
    text = "HMCH is a fund that tracks smaller companies in the UK."
    assert _sanitise_what_is_this("HMCH", text, valid) == text

