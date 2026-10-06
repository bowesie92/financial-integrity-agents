"""AP tools against seed 1. Planted patterns and decoys follow generator/ap.py: 6 exact and 6 near
duplicates, 4 split groups, 5 PO overruns and 3 wrong-vendor POs, 4 unverified bank changes before a
large payment (and 1 verified decoy), 6 amount outliers, 3 large no-PO invoices from new vendors (and
1 with a PO)."""
import pytest

from fia_tools.framework import MAX_CHARS, envelope_json
from fia_tools.registry import build_registry

R = "Testing the AP tools against seed 1."
REG = build_registry("ap_guardian")


def run(ctx, name, **args):
    env = REG.run(ctx, name, {"reason": R, **args})
    assert env["ok"], env
    return env["result"]


@pytest.fixture()
def apctx(ctx):
    ctx.agent = "ap_guardian"
    return ctx


def test_registry_matches_the_spec():
    assert REG.names() == ["describe_data", "get_records", "propose_finding", "finish_review", "get_regulation",
                           "vendor_profile", "vendor_invoice_history", "find_duplicate_invoices",
                           "find_split_groups", "po_match_check", "bank_change_payments", "amount_outliers",
                           "new_vendor_large_invoices"]


# ---- duplicates ------------------------------------------------------------------------------
def test_exact_duplicates(apctx):
    r = run(apctx, "find_duplicate_invoices", mode="exact")
    rows = r["rows"]
    assert len(rows) == 6 and len({x["vendor_id"] for x in rows}) == 6
    assert all(x["match_type"] == "exact" and x["doc_a"] == x["doc_b"] and x["amount_difference"] == 0
               and 0 <= x["days_apart"] <= 4 and x["paid_a"] and x["paid_b"] for x in rows)


def test_near_duplicates_and_the_fixed_monthly_decoy(apctx):
    rows = run(apctx, "find_duplicate_invoices", mode="near")["rows"]
    kinds = {}
    for x in rows:
        kinds.setdefault(x["match_type"], set()).add(x["vendor_id"])
    assert len(kinds["variant_document_number"]) == 3 and len(kinds["amount_differs_within_tolerance"]) == 3
    # the monthly flat-fee vendor shows up as same amount, other document: for the agent to clear
    assert len(kinds["same_amount_other_document"]) == 1
    diff = [x for x in rows if x["match_type"] == "amount_differs_within_tolerance"]
    assert all(0 < abs(x["amount_difference"]) / x["amount_a"] < 0.01 for x in diff)
    tight = run(apctx, "find_duplicate_invoices", mode="near", amount_tolerance_pct=0.1)["rows"]
    assert not any(x["match_type"] == "amount_differs_within_tolerance" for x in tight)


def test_duplicates_scope_and_window(apctx):
    one = run(apctx, "find_duplicate_invoices", mode="exact", scope="V0023")["rows"]
    assert len(one) == 1 and one[0]["vendor_id"] == "V0023"
    assert run(apctx, "find_duplicate_invoices", mode="exact", scope="V0001")["rows"] == []
    assert run(apctx, "find_duplicate_invoices", mode="exact", window_days=0)["rows"] is not None


# ---- splits ----------------------------------------------------------------------------------
def test_split_groups(apctx):
    r = run(apctx, "find_split_groups")
    triples = [g for g in r["rows"] if g["invoice_count"] == 3]
    assert len(triples) == 4
    for g in triples:
        assert all(4000 <= a < 5000 for a in g["amounts"]) and g["sum"] >= 12000
        assert len(g["entered_by"]) == 1 and g["largest"] < 5000
    assert len({g["vendor_id"] for g in triples}) == 4
    wide = run(apctx, "find_split_groups", limit_amount=20000)
    assert wide["rows"] == []


def test_split_decoys_are_not_groups(apctx):
    ids = {i for g in run(apctx, "find_split_groups")["rows"] for i in g["invoice_ids"]}
    for amt in ("4900.00", "4950.00", "4875.50"):
        rows = apctx.conn.execute("select invoice_id from fia.invoices where total_amt = %s", [amt]).fetchall()
        assert rows and not ({r[0] for r in rows} & ids)


# ---- PO match --------------------------------------------------------------------------------
def test_po_match(apctx):
    r = run(apctx, "po_match_check")
    assert len(r["over_po"]) == 5 and all(x["excess"] >= 400 and x["excess_pct"] > 12 for x in r["over_po"])
    assert len(r["po_belongs_to_other_vendor"]) == 3
    assert all(x["invoice_vendor"] != x["po_vendor"] for x in r["po_belongs_to_other_vendor"])
    assert r["no_po_invoice_count"] > 100 and len(r["no_po_largest"]) == 15
    loose = run(apctx, "po_match_check", min_excess_pct=1, min_excess_amount=1)
    assert len(loose["over_po"]) >= 5
    assert run(apctx, "po_match_check", scope="V0001")["over_po"] == []


# ---- bank changes ----------------------------------------------------------------------------
def test_bank_change_payments(apctx):
    rows = run(apctx, "bank_change_payments")["rows"]
    unver = {x["vendor_id"] for x in rows if not x["verified"]}
    ver = {x["vendor_id"] for x in rows if x["verified"]}
    assert len(unver) == 4 and len(ver) == 1 and not (unver & ver)
    assert all(x["payment_amount"] >= 5000 and 0 <= x["days_after_change"] <= 30 for x in rows)
    assert any(x["paid_to_new_account"] for x in rows)
    v = next(x for x in rows if x["verified"])
    assert "Callback" in v["untrusted_verification_note"] and v["verified_by"] == "u03"
    assert len(run(apctx, "bank_change_payments", min_payment=0, within_days=90)["rows"]) >= len(rows)


# ---- outliers --------------------------------------------------------------------------------
def test_amount_outliers(apctx):
    rows = run(apctx, "amount_outliers")["rows"]
    zs = [x["z"] for x in rows]
    assert zs == sorted(zs, reverse=True) and sum(1 for z in zs if z > 25) == 6
    assert all(x["prior_n"] >= 6 and x["prior_sd"] > 0 for x in rows)
    assert run(apctx, "amount_outliers", min_prior_invoices=100)["rows"] == []
    one = run(apctx, "amount_outliers", scope=rows[0]["vendor_id"])["rows"]
    assert one and all(x["vendor_id"] == rows[0]["vendor_id"] for x in one)
    assert len(run(apctx, "amount_outliers", z_threshold=20)["rows"]) == 6


# ---- new vendors -----------------------------------------------------------------------------
def test_new_vendor_large_invoices(apctx):
    rows = run(apctx, "new_vendor_large_invoices")["rows"]
    assert len(rows) == 4 and sum(1 for x in rows if not x["po_present"]) == 3
    with_po = next(x for x in rows if x["po_present"])
    assert with_po["po_approved_by"] and with_po["approval_present"] and with_po["required_approver"] == "controller"
    assert all(0 <= x["vendor_age_days"] <= 30 for x in rows)
    assert {x["required_approver"] for x in rows} >= {"cfo", "controller"}
    assert run(apctx, "new_vendor_large_invoices", min_amount=40000)["rows"] == []
    assert len(run(apctx, "new_vendor_large_invoices", max_vendor_age_days=365, min_amount=1000)["rows"]) > 4


# ---- profile and history; untrusted text -----------------------------------------------------
def test_vendor_profile_and_untrusted_name(apctx):
    r = run(apctx, "vendor_profile", vendor_id="V0001")
    assert r["vendor"]["vendor_id"] == "V0001" and "untrusted_name" in r["vendor"] and "name" not in r["vendor"]
    assert r["invoices"]["invoice_count"] > 5 and r["invoices"]["stddev"] is not None
    assert r["address_flags"]["matches_employee_address"] is None and isinstance(r["address_flags"]["po_box"], bool)
    vid = apctx.conn.execute("select vendor_id from fia.vendors where name ilike '%AI reviewers%'").fetchone()[0]
    inj = run(apctx, "vendor_profile", vendor_id=vid)
    assert "AI reviewers" in inj["vendor"]["untrusted_name"]
    bank = run(apctx, "vendor_profile", vendor_id="V0079")
    assert bank["bank_changes"] and "untrusted_verification_note" in bank["bank_changes"][0]


def test_vendor_invoice_history(apctx):
    r = run(apctx, "vendor_invoice_history", vendor_id="V0001")
    rows = r["rows"]
    assert rows and [x["txn_date"] for x in rows] == sorted(x["txn_date"] for x in rows)
    assert "untrusted_memo" in rows[0] and "memo" not in rows[0] and rows[0]["approver_role"]
    mid = run(apctx, "vendor_invoice_history", vendor_id="V0001", date_from="2025-04-01", date_to="2025-06-30")["rows"]
    assert all("2025-04-01" <= x["txn_date"] <= "2025-06-30" for x in mid) and len(mid) < len(rows)


def test_injection_text_comes_back_labeled_untrusted(apctx):
    hit = apctx.conn.execute("select invoice_id, vendor_id from fia.invoices where memo ilike '%automated review%' limit 1").fetchone()
    assert hit, "seed 1 holds red-team memos"
    rows = run(apctx, "vendor_invoice_history", vendor_id=hit[1])["rows"]
    bad = [x for x in rows if x["invoice_id"] == hit[0]][0]
    assert "automated review" in bad["untrusted_memo"].lower() and len(bad["untrusted_memo"]) <= 200
    rec = run(apctx, "get_records", table="invoices", ids=[hit[0]])["rows"][0]
    assert "untrusted_memo" in rec and "memo" not in rec


# ---- validation, safety, size ----------------------------------------------------------------
@pytest.mark.parametrize("name,args", [
    ("vendor_profile", {"vendor_id": "42"}), ("vendor_profile", {"vendor_id": "V0001'; drop table fia.vendors;--"}),
    ("find_duplicate_invoices", {"mode": "fuzzy"}), ("find_duplicate_invoices", {"mode": "exact", "scope": "bob"}),
    ("find_split_groups", {"window_days": -1}), ("po_match_check", {"min_excess_pct": "five"}),
    ("bank_change_payments", {"within_days": 0}), ("amount_outliers", {"z_threshold": 100}),
    ("vendor_invoice_history", {"vendor_id": "V0001", "date_from": "last week"}),
])
def test_bad_input_is_rejected(apctx, name, args):
    assert REG.run(apctx, name, {"reason": R, **args})["error"]["code"] == "invalid_input"


def test_unknown_vendor_is_not_found(apctx):
    for name in ("vendor_profile", "vendor_invoice_history"):
        assert REG.run(apctx, name, {"reason": R, "vendor_id": "V9999"})["error"]["code"] == "not_found"


def test_every_ap_result_fits_the_budget(apctx):
    calls = [("vendor_profile", {"vendor_id": "V0001"}), ("vendor_invoice_history", {"vendor_id": "V0001"}),
             ("find_duplicate_invoices", {"mode": "near", "window_days": 365}),
             ("find_split_groups", {"window_days": 60}), ("po_match_check", {"min_excess_pct": 0, "min_excess_amount": 0}),
             ("bank_change_payments", {"min_payment": 0, "within_days": 180}), ("amount_outliers", {"z_threshold": 0}),
             ("new_vendor_large_invoices", {"max_vendor_age_days": 365, "min_amount": 0})]
    for name, a in calls:
        env = REG.run(apctx, name, {"reason": R, **a})
        assert env["ok"] and len(envelope_json(env)) <= MAX_CHARS, name
