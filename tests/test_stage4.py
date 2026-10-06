"""Phase 3: the use-tax layer. A plain script must find exactly the planted exposures."""
import json
from collections import defaultdict
from decimal import Decimal

import pytest

from generator.build import build
from generator.tax import RATES, RESALE, TAXABLE


@pytest.fixture(scope="module", params=[1, 2])
def ds(request):
    d = build(request.param)
    t = d.tables
    d.state_of_site = {s["site_id"]: s["state"] for s in t["sites"]}
    d.vstate = {v["vendor_id"]: v["state"] for v in t["vendors"]}
    d.lines = defaultdict(list)
    for ln in t["invoice_lines"]:
        d.lines[ln["invoice_id"]].append(ln)
    return d


def pattern_ids(ds, pat):
    return sorted(i for m in ds.manifest if m["pattern"] == pat for i in m["record_refs"]["invoice_ids"])


def base(ds, inv):
    return sum((Decimal(l["amount"]) for l in ds.lines[inv["invoice_id"]]
                if l["account_id"] in TAXABLE), Decimal("0"))


def cross_state(ds, inv):
    return ds.vstate[inv["vendor_id"]] != ds.state_of_site[inv["site_id"]]


def test_every_invoice_has_tax_within_total(ds):
    for inv in ds.tables["invoices"]:
        tax = Decimal(inv["tax_amt"])
        assert 0 <= tax <= Decimal(inv["total_amt"]) * Decimal("0.08")


def test_detector_finds_exactly_the_planted_exposures(ds):
    found = sorted(i["invoice_id"] for i in ds.tables["invoices"]
                   if cross_state(ds, i) and Decimal(i["tax_amt"]) == 0 and base(ds, i) > 0)
    assert found == pattern_ids(ds, "use_tax_exposure")
    assert len(found) == 8


def test_decoys_are_cross_state_and_distinguishable(ds):
    inv = {i["invoice_id"]: i for i in ds.tables["invoices"]}
    for iid in pattern_ids(ds, "cross_state_tax_charged"):
        i = inv[iid]
        assert cross_state(ds, i) and Decimal(i["tax_amt"]) > 0 and base(ds, i) > 0
    for iid in pattern_ids(ds, "cross_state_resale_inventory"):
        i = inv[iid]
        assert cross_state(ds, i) and Decimal(i["tax_amt"]) == 0 and base(ds, i) == 0
        assert {l["account_id"] for l in ds.lines[iid]} <= RESALE


def test_no_other_invoice_is_cross_state(ds):
    marked = set(pattern_ids(ds, "use_tax_exposure") + pattern_ids(ds, "cross_state_tax_charged")
                 + pattern_ids(ds, "cross_state_resale_inventory"))
    assert {i["invoice_id"] for i in ds.tables["invoices"] if cross_state(ds, i)} == marked


def test_planted_exposures_spread_over_destination_states(ds):
    dests = {m["record_refs"]["destination_state"] for m in ds.manifest
             if m["pattern"] == "use_tax_exposure"}
    assert len(dests) >= 2


def test_expected_use_tax_matches_rate_and_is_material(ds):
    inv = {i["invoice_id"]: i for i in ds.tables["invoices"]}
    for m in ds.manifest:
        if m["pattern"] != "use_tax_exposure":
            continue
        r = m["record_refs"]
        i = inv[r["invoice_ids"][0]]
        assert Decimal(r["expected_use_tax"]) == (base(ds, i) * RATES[r["destination_state"]]).quantize(Decimal("0.01"))
        assert Decimal(r["expected_use_tax"]) >= Decimal("30")


def test_in_state_taxable_goods_are_taxed_at_site_state_rate(ds):
    for i in ds.tables["invoices"]:
        if cross_state(ds, i):
            continue
        b = base(ds, i)
        if b:
            r = RATES[ds.state_of_site[i["site_id"]]]
            assert abs(Decimal(i["tax_amt"]) - b * r / (1 + r)) <= Decimal("0.01")
        else:
            assert Decimal(i["tax_amt"]) == 0


def test_tax_layer_changes_no_earlier_record():
    from generator.ap import add_ap
    from generator.dataset import Dataset
    from generator.gl_clean import build_clean_gl, finalize_gl
    from generator.gl_patterns import add_decoys, add_planted
    from generator.master import build_master
    before = Dataset(1)
    build_master(before); build_clean_gl(before); add_planted(before); add_decoys(before)
    finalize_gl(before); add_ap(before)
    after = build(1)
    keep = lambda r: {k: v for k, v in r.items() if k not in ("site_id", "tax_amt")}
    assert [keep(r) for r in before.tables["invoices"]] == [keep(r) for r in after.tables["invoices"]]
    for name in ("invoice_lines", "payments", "purchase_orders", "vendors", "journal_entries", "gl_lines"):
        assert before.tables[name] == after.tables[name]
    assert after.manifest[:len(before.manifest)] == before.manifest


def test_no_label_leaks_in_text(ds):
    text = " ".join(str(i["memo"]) for i in ds.tables["invoices"]).lower()
    for word in ("use tax", "use_tax", "planted", "decoy", "cross-state", "cross_state"):
        assert word not in text


def test_deterministic():
    a, b = build(1), build(1)
    assert a.tables["invoices"] == b.tables["invoices"] and a.manifest == b.manifest
