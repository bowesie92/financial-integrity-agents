"""Stage 2 checks: planted GL patterns and decoys against the ground-truth manifest."""
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from generator import config as C
from generator.build import build
from generator.calendar_util import business_days, month_bounds
from generator.stats import first_digit_mad

EXPECTED = {
    "benford_violation": 1, "round_dollar_cluster": 60, "after_hours_postings": 40,
    "post_close_thin_description": 25, "unusual_user_account": 15,
    "recurring_identical_entries": 36, "controller_month_end_weekend": 8,
    "fresno_local_hours": 10, "post_close_cfo_approved": 1,
}


@pytest.fixture(scope="module", params=[1, 2])
def ds(request):
    d = build(request.param)
    d.manifest = [m for m in d.manifest if m["agent"] == "gl_sentinel"]
    d.je = {j["je_id"]: j for j in d.tables["journal_entries"]}
    d.lines = defaultdict(list)
    for ln in d.tables["gl_lines"]:
        d.lines[ln["je_id"]].append(ln)
    d.tz = {s["site_id"]: ZoneInfo(s["timezone"]) for s in d.tables["sites"]}
    d.close = {p["period_id"]: date.fromisoformat(p["close_date"]) for p in d.tables["periods"]}
    return d


def refs(ds, pattern):
    return [i for m in ds.manifest if m["pattern"] == pattern for i in m["record_refs"]["je_ids"]]


def local(ds, je_id):
    j = ds.je[je_id]
    return datetime.fromisoformat(j["posted_at"]).astimezone(ds.tz[j["site_id"]])


def total(ds, je_id):
    return sum(Decimal(ln["debit"]) for ln in ds.lines[je_id])


def test_deterministic():
    def digest(d):
        return hashlib.sha256(json.dumps([d.tables, d.manifest], sort_keys=True,
                                         default=str).encode()).hexdigest()
    assert digest(build(1)) == digest(build(1))


def test_manifest_counts(ds):
    counts = defaultdict(int)
    for m in ds.manifest:
        counts[m["pattern"]] += 1
        assert m["agent"] == "gl_sentinel"
        assert m["kind"] in ("planted", "decoy")
    assert dict(counts) == EXPECTED
    assert all(i in ds.je for m in ds.manifest for i in m["record_refs"]["je_ids"])


def test_volume_close_to_scope(ds):
    assert 14_500 <= len(ds.je) <= 15_500
    assert 44_000 <= len(ds.tables["gl_lines"]) <= 47_500


def test_all_entries_balance_and_have_unique_ids(ds):
    assert len(ds.je) == len(ds.tables["journal_entries"])
    for je_id, lines in ds.lines.items():
        assert sum(Decimal(ln["debit"]) - Decimal(ln["credit"]) for ln in lines) == 0
    assert set(ds.lines) == set(ds.je)


def test_benford_only_q3_fails(ds):
    by_q = defaultdict(list)
    for ln in ds.tables["gl_lines"]:
        q = (int(ds.je[ln["je_id"]]["entry_date"][5:7]) - 1) // 3 + 1
        by_q[q].append(ln["debit"] if Decimal(ln["debit"]) > 0 else ln["credit"])
    for q, amts in by_q.items():
        mad, n = first_digit_mad(amts)
        assert n >= 5_000
        if q == 3:
            assert mad > 0.015, mad
        else:
            assert mad < 0.006, (q, mad)


def test_benford_entries_are_manual_q3_by_one_user(ds):
    ids = refs(ds, "benford_violation")
    assert len(ids) == 380
    assert {ds.je[i]["posted_by"] for i in ids} == {"u06"}
    assert all(ds.je[i]["source"] == "manual" and "2025-07" <= ds.je[i]["period_id"] <= "2025-09"
               for i in ids)


def test_round_dollar_cluster(ds):
    ids = refs(ds, "round_dollar_cluster")
    ends = set()
    for m in (3, 6, 9, 12):
        ends |= set(business_days(*month_bounds(C.YEAR, m))[-2:])
    for i in ids:
        (ln,) = [x for x in ds.lines[i] if Decimal(x["debit"]) > 0]
        amt = Decimal(ln["debit"])
        assert amt % 1000 == 0 and ln["account_id"] == "6960"
        assert ds.je[i]["posted_by"] == "u03"
        assert date.fromisoformat(ds.je[i]["entry_date"]) in ends
    # Round-dollar amounts of $1,000 multiples are rare elsewhere, except the rent decoy.
    rent = set(refs(ds, "recurring_identical_entries"))
    other = 0
    for ln in ds.tables["gl_lines"]:
        a = Decimal(ln["debit"])
        if a >= 1000 and a % 1000 == 0 and ln["je_id"] not in ids and ln["je_id"] not in rent:
            other += 1
    assert other <= 10


def test_after_hours_detector_finds_exactly_planted_and_controller_decoys(ds):
    flagged = set()
    for je_id, j in ds.je.items():
        t = local(ds, je_id)
        if t.weekday() >= 5 or not (C.BUSINESS_START_HOUR <= t.hour < C.BUSINESS_END_HOUR):
            flagged.add(je_id)
    assert flagged == set(refs(ds, "after_hours_postings")) | \
        set(refs(ds, "controller_month_end_weekend"))
    assert {ds.je[i]["posted_by"] for i in refs(ds, "after_hours_postings")} == {"u05"}
    assert {ds.je[i]["posted_by"] for i in refs(ds, "controller_month_end_weekend")} == {"u01"}


def test_fresno_decoys_inside_local_hours_but_odd_in_utc(ds):
    ids = refs(ds, "fresno_local_hours")
    assert {ds.je[i]["posted_by"] for i in ids} == {"u09"}
    fridays = 0
    for i in ids:
        t = local(ds, i)
        assert t.hour == 18 and t.weekday() < 5
        fridays += t.weekday() == 4
    assert fridays >= 4
    utc = [datetime.fromisoformat(ds.je[i]["posted_at"]) for i in ids]
    assert any(u.hour < C.BUSINESS_START_HOUR or u.weekday() >= 5 for u in utc)


def test_post_close_detector_finds_exactly_planted_and_cfo_decoy(ds):
    late = {i for i, j in ds.je.items()
            if datetime.fromisoformat(j["posted_at"]).astimezone(ds.tz[j["site_id"]]).date()
            > ds.close[j["period_id"]]}
    planted = set(refs(ds, "post_close_thin_description"))
    decoy = set(refs(ds, "post_close_cfo_approved"))
    assert late == planted | decoy
    for i in planted:
        d = ds.je[i]["description"]
        assert d is None or len(d) <= 8
        assert datetime.fromisoformat(ds.je[i]["posted_at"]).date() <= C.AS_OF
    (i,) = decoy
    assert len(ds.je[i]["description"]) > 40 and ds.je[i]["approved_by"] == C.CFO


def test_unusual_user_account(ds):
    ids = refs(ds, "unusual_user_account")
    assert {ds.je[i]["posted_by"] for i in ids} == {"u11"}
    for i in ids:
        assert any(ln["account_id"] == "1500" for ln in ds.lines[i])
        assert total(ds, i) >= 5_000
    others = defaultdict(set)    # who else ever posts to 1500
    for ln in ds.tables["gl_lines"]:
        if ln["account_id"] == "1500" and ln["je_id"] not in ids:
            others[ds.je[ln["je_id"]]["posted_by"]].add(ln["je_id"])
    assert "u11" not in others and not set(others) - {"u01", "u03", "u04"}
    assert not any(ds.je[i]["posted_by"] == "u11" and ln["account_id"] == "1500"
                   for i in ds.je if i not in ids for ln in ds.lines[i])


def test_recurring_decoys_are_identical(ds):
    ids = refs(ds, "recurring_identical_entries")
    rent = [i for i in ids if any(ln["account_id"] == "6100" for ln in ds.lines[i])]
    pay = [i for i in ids if ds.je[i]["source"] == "payroll"]
    assert len(rent) == 12 and len(pay) == 24
    assert len({tuple(sorted((ln["account_id"], ln["debit"], ln["credit"])
                             for ln in ds.lines[i])) for i in rent}) == 1
    assert len({tuple(sorted((ln["account_id"], ln["debit"], ln["credit"])
                             for ln in ds.lines[i])) for i in pay}) == 1


def test_approval_limits_hold_everywhere(ds):
    for i, j in ds.je.items():
        t, ap = total(ds, i), j["approved_by"]
        assert ap != j["posted_by"]
        if t >= C.CFO_LIMIT:
            assert ap == C.CFO
        elif t >= C.CONTROLLER_LIMIT:
            assert ap in (C.CONTROLLER, C.CFO)


def test_no_entry_posted_after_as_of(ds):
    assert all(datetime.fromisoformat(j["posted_at"]).date() <= C.AS_OF for j in ds.je.values())
    assert all(j["entry_date"].startswith(str(C.YEAR)) for j in ds.je.values())
