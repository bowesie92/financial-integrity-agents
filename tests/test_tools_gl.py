"""GL tools against seed 1. The planted users come from the generator's pattern design:
u06 Benford (Q3), u03 round dollars, u05 weekend and after hours, u07 and u08 post-close with thin
descriptions, u11 unusual asset postings. Decoys must not be explained away by the tools."""
import math

import pytest

from fia_tools import analytics as A
from fia_tools.registry import build_registry

R = "Testing the GL tools against seed 1."
REG = build_registry("gl_sentinel")


def run(ctx, name, **args):
    env = REG.run(ctx, name, {"reason": R, **args})
    assert env["ok"], env
    return env["result"]


# ---- analytics (pure) ------------------------------------------------------------------------
def test_benford_math_and_bands():
    perfect = {d: round(100000 * math.log10(1 + 1 / d)) for d in range(1, 10)}
    s = A.first_digit_stats(perfect)
    assert s["band"] == "close" and s["mad"] < 0.001 and s["sufficient_sample"]
    skew = {d: 1000 for d in range(1, 10)}
    assert A.first_digit_stats(skew)["band"] == "nonconforming"
    assert [A.mad_band(x) for x in (0.005, 0.006, 0.011, 0.012, 0.014, 0.015, 0.02)] == [
        "close", "acceptable", "acceptable", "marginal", "marginal", "nonconforming", "nonconforming"]
    assert A.first_digit_stats({})["n"] == 0


def test_digit_helpers():
    assert (A.first_digit("1234.50"), A.first_two_digits("1234.50")) == (1, 12)
    assert (A.first_digit("5.25"), A.first_two_digits("5.25")) == (5, 52)
    assert A.first_digit("0.99") is None
    assert A.is_round_multiple("3000.00") and not A.is_round_multiple("3000.01")


def test_first_two_ranks_by_z():
    counts = {p: 100 for p in range(10, 100)}
    counts[57] = 400
    out = A.first_two_stats(counts, top=3)
    assert out["pairs"][0]["digits"] == 57 and out["pairs"][0]["direction"] == "excess"


def test_timing_flags_use_local_time():
    from datetime import date, datetime, timezone
    # 02:00 UTC Tuesday is 19:00 Monday in Phoenix (after hours, not weekend) ...
    t = datetime(2025, 7, 15, 2, 0, tzinfo=timezone.utc)
    assert A.timing_flags(t, "America/Phoenix", date(2025, 7, 31), date(2025, 8, 7)) == ["after_hours"]
    # ... and 10:00 local in Fresno (17:00 UTC) is ordinary, though a UTC reading would say otherwise.
    t = datetime(2025, 7, 15, 3, 0, tzinfo=timezone.utc)   # 20:00 Monday Fresno summer: after hours
    assert "after_hours" in A.timing_flags(t, "America/Los_Angeles", date(2025, 7, 31), date(2025, 8, 7))
    t = datetime(2025, 7, 15, 14, 0, tzinfo=timezone.utc)  # 07:00 Fresno
    assert A.timing_flags(t, "America/Los_Angeles", date(2025, 7, 31), date(2025, 8, 7)) == []
    t = datetime(2025, 7, 4, 17, 0, tzinfo=timezone.utc)   # July 4 holiday, 10:00 Phoenix
    assert A.timing_flags(t, "America/Phoenix", date(2025, 7, 31), date(2025, 8, 7)) == ["holiday"]
    t = datetime(2025, 8, 11, 17, 0, tzinfo=timezone.utc)   # after the Aug 7 close
    assert "post_close" in A.timing_flags(t, "America/Phoenix", date(2025, 7, 31), date(2025, 8, 7))


# ---- population and Benford ------------------------------------------------------------------
def test_profile_whole_data_and_quarter(ctx):
    r = run(ctx, "gl_population_profile")
    assert r["record_count"] == 45828 and r["sufficient_for_benford"]
    q = run(ctx, "gl_population_profile", quarter="2025-Q3")
    assert 9000 < q["record_count"] < 14000 and 0 < q["manual_entry_share"] < 1
    small = run(ctx, "gl_population_profile", period_id="2025-07", source="payroll")
    assert not small["sufficient_for_benford"]
    assert run(ctx, "gl_population_profile", site_id=3)["record_count"] == 4618


def test_planted_benford_quarter_is_nonconforming_and_clean_quarters_are_close(ctx):
    q3 = run(ctx, "benford_first_digit", quarter="2025-Q3")
    assert q3["band"] == "nonconforming" and 0.021 < q3["mad"] < 0.023 and q3["sufficient_sample"]
    for q in ("2025-Q1", "2025-Q2", "2025-Q4"):
        r = run(ctx, "benford_first_digit", quarter=q)
        assert r["band"] == "close" and r["mad"] < 0.006, (q, r["mad"])
    assert [d["digit"] for d in q3["digits"]] == list(range(1, 10))


def test_small_subset_is_flagged_insufficient(ctx):
    r = run(ctx, "benford_first_digit", period_id="2025-07", account_class="revenue")
    assert r["sufficient_sample"] is False


def test_first_two_digits_finds_the_fabricated_range(ctx):
    r = run(ctx, "benford_first_two_digits", quarter="2025-Q3", top=10)
    assert len(r["pairs"]) == 10
    zs = [p["z"] for p in r["pairs"]]
    assert zs == sorted(zs, reverse=True) and zs[0] > 5
    assert any(p["direction"] == "excess" and p["digits"] >= 50 for p in r["pairs"])


# ---- round dollars ---------------------------------------------------------------------------
def test_round_dollar_scan_by_user_ranks_u03_first(ctx):
    r = run(ctx, "round_dollar_scan")
    top = r["rows"][0]
    assert top["group"] == "u03" and top["round_lines"] >= 55 and top["share_of_group"] > 0.04
    assert len(set(top["sample_je_ids"])) == 5 and r["population_lines"] == 45828
    assert top["round_entries"] == 60 and top["round_lines"] == 120
    by_acct = run(ctx, "round_dollar_scan", group_by="account")
    assert by_acct["rows"][0]["group"] == "6960" and by_acct["rows"][0]["share_of_group"] > 0.5


def test_round_dollar_scan_floor_and_day(ctx):
    r = run(ctx, "round_dollar_scan", group_by="day", quarter="2025-Q1")
    assert r["rows"] and all(row["round_lines"] >= 1 for row in r["rows"])
    huge = run(ctx, "round_dollar_scan", min_amount=1_000_000)
    assert huge["round_lines"] == 0 and huge["rows"] == []


# ---- timing ----------------------------------------------------------------------------------
def test_after_hours_and_weekend_find_u05_not_the_fresno_decoy(ctx):
    ah = run(ctx, "timing_scan", rule="after_hours")
    assert ah["rows"][0]["group"] == "u05" and ah["rows"][0]["flagged"] >= 20
    assert all(r["group"] in ("u05",) or r["flagged"] <= 3 for r in ah["rows"])
    wk = run(ctx, "timing_scan", rule="weekend")
    assert wk["rows"][0]["group"] == "u05" and wk["rows"][0]["flagged"] >= 18
    assert any(r["group"] == "u01" for r in wk["rows"])     # the controller decoy shows up for review
    site3 = run(ctx, "timing_scan", rule="after_hours", group_by="site")
    assert next((r for r in site3["rows"] if r["group"] == 3), {"flagged": 0})["flagged"] <= 3  # Fresno local hours are fine


def test_post_close_finds_u07_and_u08(ctx):
    pc = run(ctx, "timing_scan", rule="post_close")
    groups = {r["group"]: r["flagged"] for r in pc["rows"]}
    assert groups["u07"] >= 14 and groups["u08"] >= 9
    ids = pc["rows"][0]["sample_je_ids"]
    assert 1 <= len(ids) <= 5


def test_timing_scan_filters_and_rules(ctx):
    r = run(ctx, "timing_scan", rule="last_3_days_of_period", quarter="2025-Q3", source="manual")
    assert r["population_entries"] > 0 and r["flagged_entries"] <= r["population_entries"]
    assert run(ctx, "timing_scan", rule="holiday")["flagged_entries"] >= 0


# ---- user profile ----------------------------------------------------------------------------
def test_role_peer_comparison_surfaces_u11_asset_postings(ctx):
    p = run(ctx, "user_account_profile", user_id="u11")
    rare = p["accounts_not_used_by_role_peers"]
    assert p["user"]["role"] == "ap_clerk" and p["peer_count"] == 3
    assert [r["account_id"] for r in rare] == ["1500"] and rare[0]["account_class"] == "asset"
    assert rare[0]["lines"] == 15 and rare[0]["share_of_user_lines"] < 0.05
    assert "new_account_lines" not in p and "note" in p


def test_new_account_lines_catch_u03_round_dollar_account(ctx):
    r = run(ctx, "user_account_profile", user_id="u03", period_id="2025-03")
    assert any(x["account_id"] == "6960" for x in r["new_account_lines"])
    assert len(r["window_periods"]) == 2 and r["has_history"]
    later = run(ctx, "user_account_profile", user_id="u03", period_id="2025-04")
    assert not any(x["account_id"] == "6960" for x in later["new_account_lines"])   # no longer new
    whole = run(ctx, "user_account_profile", user_id="u03")
    assert {"6950", "6960"} <= {x["account_id"] for x in whole["accounts_not_used_by_role_peers"]}


def test_user_account_profile_edges(ctx):
    first = run(ctx, "user_account_profile", user_id="u06", period_id="2025-01")
    assert first["has_history"] is False and first["new_class_lines"] == [] and "note" in first
    sole = run(ctx, "user_account_profile", user_id="u01")      # only controller: no peers to compare
    assert sole["peer_count"] == 0 and sole["accounts_not_used_by_role_peers"] == []
    for args, code in [({"user_id": "u99"}, "not_found"), ({"user_id": "u01", "period_id": "2031-01"}, "not_found"),
                       ({"user_id": "bob"}, "invalid_input")]:
        assert REG.run(ctx, "user_account_profile", {"reason": R, **args})["error"]["code"] == code


# ---- list_journal_entries --------------------------------------------------------------------
def test_list_entries_by_user_and_description(ctx):
    r = run(ctx, "list_journal_entries", posted_by="u07", has_description=False)
    assert 10 <= len(r["rows"]) <= 50
    row = r["rows"][0]
    assert row["posted_by"] == "u07" and "untrusted_description" in row and row["total_amount"] > 0
    assert all(not x["untrusted_description"] for x in r["rows"])
    on_acct = run(ctx, "list_journal_entries", account_id="6960", min_amount=1000)
    assert on_acct["rows"] and all("6960" in x["accounts"] for x in on_acct["rows"])


def test_list_entries_needs_a_filter_and_caps_rows(ctx):
    assert REG.run(ctx, "list_journal_entries", {"reason": R})["error"]["code"] == "invalid_input"
    big = REG.run(ctx, "list_journal_entries", {"reason": R, "source": "manual"})
    assert big["ok"] and big["row_count"] <= 50 and big["truncated"] is True or big["result"]["more_available"]
    dated = run(ctx, "list_journal_entries", date_from="2025-03-31", date_to="2025-03-31", posted_by="u03")
    assert all(x["entry_date"] == "2025-03-31" for x in dated["rows"])


def test_filter_validation_and_conflicts(ctx):
    e = REG.run(ctx, "benford_first_digit", {"reason": R, "period_id": "2025-07", "quarter": "2025-Q3"})
    assert e["error"]["code"] == "invalid_input" and "not both" in e["error"]["message"]
    assert REG.run(ctx, "benford_first_digit", {"reason": R, "quarter": "Q3"})["error"]["code"] == "invalid_input"
    assert REG.run(ctx, "timing_scan", {"reason": R})["error"]["code"] == "invalid_input"
    assert REG.run(ctx, "round_dollar_scan", {"reason": R, "group_by": "vendor"})["error"]["code"] == "invalid_input"


def test_no_sql_injection_through_filters(ctx):
    e = REG.run(ctx, "list_journal_entries", {"reason": R, "posted_by": "u06'; drop table fia.gl_lines;--"})
    assert e["ok"] is False and e["error"]["code"] == "invalid_input"
    assert run(ctx, "gl_population_profile")["record_count"] == 45828


def test_every_result_fits_the_budget(ctx):
    from fia_tools.framework import MAX_CHARS, envelope_json
    for name, a in [("gl_population_profile", {}), ("benford_first_digit", {"quarter": "2025-Q3"}),
                    ("round_dollar_scan", {"group_by": "day"}), ("timing_scan", {"rule": "weekend"}),
                    ("list_journal_entries", {"source": "manual"})]:
        env = REG.run(ctx, name, {"reason": R, **a})
        assert len(envelope_json(env)) <= MAX_CHARS, name
