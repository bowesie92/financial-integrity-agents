"""Rules-only baseline. V1 thresholds are pinned to docs/metrics.md section 5 as written in Phase 1 and V2
to Amendment 1; the DB tests run the rules on seed 1 and check known planted ids are found, that the result is deterministic, and that
the baseline writes nothing."""
import json

import pytest

from baseline import rules, score
from baseline.run import run

RULE_NAMES = set(rules.ALL_RULES)


def test_v1_thresholds_are_the_ones_fixed_in_metrics():
    t = rules.THRESHOLDS_V1
    assert t["benford_mad_above"] == 0.015
    assert (t["round_min_amount"], t["round_multiple"], t["round_min_entries_per_month"]) == (1000, 1000, 20)
    assert (t["pairing_min_amount"], t["pairing_history_periods"]) == (5000, 6)
    assert (t["exact_window_days"], t["near_window_days"], t["near_tolerance_pct"]) == (30, 30, 1)
    assert (t["split_window_days"], t["split_limit"]) == (7, 5000)
    assert (t["new_vendor_max_age_days"], t["new_vendor_min_amount"]) == (29, 5000)
    assert (t["po_excess_pct"], t["po_excess_dollars"]) == (5, 100)
    assert (t["outlier_z"], t["outlier_min_prior"]) == (3, 6)
    assert (t["bank_change_within_days"], t["bank_change_min_payment"]) == (30, 5000)


def test_v2_changes_only_the_two_amended_rules():
    v1, v2 = rules.THRESHOLDS_V1, rules.THRESHOLDS_V2
    changed = {k for k in v1 if v1[k] != v2[k]}
    assert changed == {"round_min_entries_per_month", "pairing_rule", "pairing_max_user_share"}
    assert v2["round_min_entries_per_month"] == 5
    assert (v2["pairing_rule"], v2["pairing_max_user_share"]) == ("peer_rarity", 0.01)


def test_rule_lists_cover_the_twelve_metric_lines():
    assert len(rules.ALL_RULES) == 12 and len(set(rules.ALL_RULES)) == 12


# ---- scoring (no database) ---------------------------------------------------------------
def _f(rule, **refs):
    return {"rule": rule, "agent": "x", "refs": refs, "detail": {}}


def _m(kind, pattern, **refs):
    return {"kind": kind, "agent": "x", "pattern": pattern, "record_refs": refs}


def test_score_matches_by_overlap_and_counts_decoys():
    findings = [_f("exact_duplicate", invoice_ids=["A1", "A2"]), _f("timing", je_ids=["J9"]),
                _f("outlier", invoice_ids=["A7"])]
    manifest = [_m("planted", "exact_duplicate", invoice_ids=["A2", "A3"]),
                _m("planted", "split_invoices", invoice_ids=["B1"]),
                _m("decoy", "controller_month_end_weekend", je_ids=["J9"]),
                _m("decoy", "fresno_local_hours", je_ids=["J10"])]
    s = score.score(findings, manifest)
    assert s["planted"]["exact_duplicate"]["found"] == 1
    assert s["planted"]["split_invoices"]["found"] == 0
    assert s["decoys"]["controller_month_end_weekend"]["cleared"] == 0.0
    assert s["decoys"]["fresno_local_hours"]["cleared"] == 1.0
    assert s["rules"]["exact_duplicate"]["precision"] == 1.0
    assert s["rules"]["timing"]["decoy"] == 1 and s["rules"]["outlier"]["unmatched"] == 1


def test_score_benford_by_quarter_and_no_rule_patterns_never_count():
    manifest = [_m("planted", "benford_violation", je_ids=["J1"]),
                _m("planted", "use_tax_exposure", invoice_ids=["A1"])]
    s = score.score([_f("benford", quarter="2025-Q3"), _f("exact_duplicate", invoice_ids=["A1"])], manifest)
    assert s["planted"]["benford_violation"]["found"] == 1
    assert s["planted"]["use_tax_exposure"]["found"] == 0
    s2 = score.score([_f("benford", quarter="2025-Q1")], manifest)
    assert s2["planted"]["benford_violation"]["found"] == 0


# ---- seed 1 (database) -------------------------------------------------------------------
@pytest.fixture(scope="module")
def result(agent_conn):
    return run("test")


def _ids(result, rule):
    return [set(f["refs"].get("je_ids", []) + f["refs"].get("invoice_ids", [])) for f in result["findings"]
            if f["rule"] == rule]


def _found(result, rule, wanted):
    return any(set(wanted) <= s for s in _ids(result, rule))


def test_finding_shape_and_json_round_trip(result):
    assert result["findings"], "baseline found nothing"
    for f in result["findings"]:
        assert f["rule"] in RULE_NAMES and f["agent"] in ("gl_sentinel", "ap_guardian")
        assert f["refs"] and isinstance(f["detail"], dict)
    json.dumps(result, default=str)
    assert set(result["counts"]) == RULE_NAMES


def test_deterministic(result):
    again = run("test")
    assert again["findings"] == result["findings"]


def test_benford_flags_only_the_planted_quarter(result):
    bf = [f for f in result["findings"] if f["rule"] == "benford"]
    assert [f["refs"]["quarter"] for f in bf] == ["2025-Q3"]
    assert bf[0]["detail"]["mad"] > 0.015 and bf[0]["detail"]["sufficient_sample"]


def test_known_planted_items_are_found(result):
    assert _found(result, "exact_duplicate", ["AP-000650", "AP-000651"])
    assert _found(result, "split", ["AP-001385", "AP-001389", "AP-001405"])
    assert _found(result, "outlier", ["AP-001074"])
    assert _found(result, "po_mismatch", ["AP-001305"])
    assert _found(result, "new_vendor", ["AP-000386"])
    assert _found(result, "bank_change", ["AP-001189"])
    assert _found(result, "post_close", ["JE-2025-007905"])
    assert _found(result, "timing", ["JE-2025-007277"])


def test_v1_leaves_two_planted_gl_patterns_unflagged(result):
    """Documented in docs/baseline_notes.md: the round-dollar rule needs 20 entries in a month but the
    planted cluster is 15 per quarter-end month, and the pairing rule needs a class unused for 6 months
    but the planted user posts to the asset class most months. This is why Amendment 1 exists."""
    assert result["version"] == "v1"
    assert not any(f["rule"] in ("round_dollar", "user_account_pairing") for f in result["findings"])


@pytest.fixture(scope="module")
def result2(agent_conn):
    return run("test", "v2")


def test_v2_round_dollar_finds_the_planted_user_months(result2):
    rd = [f for f in result2["findings"] if f["rule"] == "round_dollar"]
    assert sorted((f["detail"]["user"], f["detail"]["period"]) for f in rd) == [
        ("u03", "2025-03"), ("u03", "2025-06"), ("u03", "2025-09"), ("u03", "2025-12")]
    assert all(f["detail"]["round_entries"] >= 5 for f in rd)


def test_v2_pairing_finds_u11_and_skips_automated_postings(result2):
    pf = [f for f in result2["findings"] if f["rule"] == "user_account_pairing"]
    assert any("JE-2025-000347" in f["refs"]["je_ids"] for f in pf)
    assert sum(f["detail"]["user"] == "u11" for f in pf) == 15
    assert not any(f["detail"]["user"] == "u24" for f in pf)
    assert all(l["user_share"] < 0.01 for f in pf for l in f["detail"]["lines"])


def test_v2_differs_from_v1_only_in_the_two_amended_rules(result, result2):
    keep = lambda r: [f for f in r["findings"] if f["rule"] not in ("round_dollar", "user_account_pairing")]
    assert keep(result) == keep(result2)
    assert result2["version"] == "v2" and result2["thresholds"] == rules.THRESHOLDS_V2


def test_timing_rule_excludes_post_close_and_period_end_flags(result):
    for f in result["findings"]:
        if f["rule"] == "timing":
            assert set(f["detail"]["flags"]) <= {"weekend", "holiday", "after_hours"}


def test_baseline_writes_nothing(agent_conn):
    n = agent_conn.execute("select count(*) from fia.findings").fetchone()[0]
    run("test")
    assert agent_conn.execute("select count(*) from fia.findings").fetchone()[0] == n
