import json
from decimal import Decimal

from fia_tools.regulation import STATES, get_regulation, topics, _load
from generator.tax import RATES


def test_every_state_has_every_topic():
    for st in STATES:
        for tp in topics():
            assert "rows" in get_regulation(st, tp)


def test_rows_have_source_and_date():
    for r in _load()["rows"]:
        assert r["source_url"].startswith("https://") and r["as_of"] == "2026-10-05"
        assert any(r["source_url"].startswith(p) for p in
                   ("https://azdor.gov", "https://comptroller.texas.gov", "https://cdtfa.ca.gov"))


def test_rates_match_the_generator():
    for st in STATES:
        row = get_regulation(st, "use_tax_rate")["rows"][0]
        assert Decimal(row["rate"]) == RATES[st]


def test_label_is_always_present():
    assert "not legal" in get_regulation("az", "use_tax_rate")["label"].lower()


def test_unknown_input_returns_error_not_a_guess():
    assert "error" in get_regulation("NV", "use_tax_rate")
    assert "error" in get_regulation("AZ", "unclaimed_property")
    assert "error" in get_regulation(None, None)


def test_case_and_whitespace_are_forgiven():
    assert get_regulation(" tx ", " USE_TAX_RATE ")["state"] == "TX"
