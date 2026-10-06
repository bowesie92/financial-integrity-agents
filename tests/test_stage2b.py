"""Stage 2 fixes: no text leaks, the pairing rule, and the Benford sample-size decision."""
from collections import Counter, defaultdict
from decimal import Decimal

import pytest

from generator import config as C
from generator.build import build
from generator.gl_clean import ACCT_CLASS

# Descriptions that are naturally specific to one kind of entry and need no pool.
NATURAL = {"Monthly rent, Phoenix HQ and warehouse", "Payroll run"}


@pytest.fixture(scope="module", params=[1, 2])
def ds(request):
    d = build(request.param)
    d.je = {j["je_id"]: j for j in d.tables["journal_entries"]}
    d.tag = {}
    for m in d.manifest:
        if m["agent"] == "gl_sentinel":
            for i in m["record_refs"]["je_ids"]:
                d.tag[i] = m["pattern"]
    return d


def test_planted_descriptions_come_from_the_normal_pool(ds):
    pool = Counter(j["description"] for i, j in ds.je.items() if i not in ds.tag)
    for i, pattern in ds.tag.items():
        d = ds.je[i]["description"]
        if pattern == "post_close_thin_description" or d in NATURAL or d.startswith("Post-close"):
            continue
        assert pool[d] >= 20, (pattern, d)


def test_pairing_rule_peer_and_rarity(ds):
    ids = {i for i, p in ds.tag.items() if p == "unusual_user_account"}
    by_user = defaultdict(set)
    hits = defaultdict(set)
    for ln in ds.tables["gl_lines"]:
        u = ds.je[ln["je_id"]]["posted_by"]
        by_user[u].add(ln["je_id"])
        if ln["account_id"] == "1500":
            hits[u].add(ln["je_id"])
    roles = {u["user_id"]: u["role"] for u in ds.tables["users"]}
    clerks = [u for u, r in roles.items() if r == "ap_clerk"]
    assert [u for u in clerks if hits[u]] == ["u11"]             # no peer posts to 1500
    assert len(hits["u11"]) / len(by_user["u11"]) < 0.01        # and it is rare for u11
    assert hits["u11"] == ids


def test_rent_is_not_a_human_pairing(ds):
    posters = set()
    for ln in ds.tables["gl_lines"]:
        if ln["account_id"] in ("6100", "6000", "6010", "6020"):
            posters.add(ds.je[ln["je_id"]]["posted_by"])
    assert posters == {C.SYSTEM_USER}


def test_sample_size_floor_shapes_the_benford_scope(ds):
    q3_all, q3_exp, q3_u06 = 0, 0, 0
    for ln in ds.tables["gl_lines"]:
        j = ds.je[ln["je_id"]]
        if "2025-07" <= j["period_id"] <= "2025-09":
            q3_all += 1
            if ACCT_CLASS[ln["account_id"]] == "expense" and Decimal(ln["debit"]) > 0:
                q3_exp += 1
            if j["posted_by"] == "u06":
                q3_u06 += 1
    assert q3_all >= 5_000          # the formal test runs on all lines in the quarter
    assert q3_exp < 5_000           # expense-only is below the floor
    assert q3_u06 < 5_000           # one-user drill-down is descriptive evidence only
