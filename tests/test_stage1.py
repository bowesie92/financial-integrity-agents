"""Stage 1 checks: master data and the clean general ledger."""
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from generator import config as C
from generator.build import build_clean as build
from generator.stats import first_digit_mad

SEEDS = [1, 2]


@pytest.fixture(scope="module", params=SEEDS)
def ds(request):
    return build(request.param)


def _digest(d):
    blob = json.dumps(d.tables, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def test_same_seed_same_data():
    assert _digest(build(1)) == _digest(build(1))


def test_different_seeds_differ():
    assert _digest(build(1)) != _digest(build(2))


def test_volumes(ds):
    t = ds.tables
    assert len(t["journal_entries"]) == C.N_CLEAN_JES
    assert 41_000 <= len(t["gl_lines"]) <= 47_000
    assert len(t["vendors"]) == C.N_VENDORS
    assert len(ds.meta["new_vendor_ids"]) == C.N_NEW_VENDORS_2025


def test_every_entry_balances_and_lines_are_one_sided(ds):
    sums = defaultdict(Decimal)
    for ln in ds.tables["gl_lines"]:
        d, c = Decimal(ln["debit"]), Decimal(ln["credit"])
        assert d >= 0 and c >= 0 and (d == 0 or c == 0)
        sums[ln["je_id"]] += d - c
    assert all(v == 0 for v in sums.values())
    assert set(sums) == {j["je_id"] for j in ds.tables["journal_entries"]}


def test_foreign_keys_resolve(ds):
    t = ds.tables
    users = {u["user_id"] for u in t["users"]}
    accts = {a["account_id"] for a in t["accounts"]}
    periods = {p["period_id"] for p in t["periods"]}
    for j in t["journal_entries"]:
        assert j["posted_by"] in users and j["period_id"] in periods
        assert j["approved_by"] is None or j["approved_by"] in users
    assert all(ln["account_id"] in accts for ln in t["gl_lines"])
    assert all(v["created_by"] in users for v in t["vendors"])


def test_clean_postings_are_weekday_business_hours_local(ds):
    tz = {s["site_id"]: ZoneInfo(s["timezone"]) for s in ds.tables["sites"]}
    for j in ds.tables["journal_entries"]:
        local = datetime.fromisoformat(j["posted_at"]).astimezone(tz[j["site_id"]])
        assert local.weekday() < 5 and local.date() not in C.HOLIDAYS
        assert C.BUSINESS_START_HOUR <= local.hour < C.BUSINESS_END_HOUR
        assert local.date().isoformat() == j["entry_date"]


def test_clean_entries_posted_before_close(ds):
    close = {p["period_id"]: date.fromisoformat(p["close_date"]) for p in ds.tables["periods"]}
    for j in ds.tables["journal_entries"]:
        assert datetime.fromisoformat(j["posted_at"]).date() <= close[j["period_id"]]


def test_approval_limits_respected(ds):
    totals = defaultdict(Decimal)
    for ln in ds.tables["gl_lines"]:
        totals[ln["je_id"]] += Decimal(ln["debit"])
    for j in ds.tables["journal_entries"]:
        tot, ap = totals[j["je_id"]], j["approved_by"]
        assert ap != j["posted_by"]
        if tot >= C.CFO_LIMIT:
            assert ap == C.CFO
        elif tot >= C.CONTROLLER_LIMIT:
            assert ap in (C.CONTROLLER, C.CFO)


def test_users_only_use_their_own_accounts(ds):
    prof = ds.meta["profiles"]
    by_je = {j["je_id"]: j["posted_by"] for j in ds.tables["journal_entries"]}
    for ln in ds.tables["gl_lines"]:
        u = by_je[ln["je_id"]]
        allowed = {a for a, _ in prof[u]["debit"]} | {a for a, _ in prof[u]["credit"]}
        assert ln["account_id"] in allowed


def test_seldom_accounts_are_seldom(ds):
    n = sum(1 for ln in ds.tables["gl_lines"] if ln["account_id"] in C.SELDOM_ACCOUNTS)
    assert 5 <= n <= 150


def test_round_dollar_rate_is_low(ds):
    amts = [Decimal(ln["debit"]) for ln in ds.tables["gl_lines"] if Decimal(ln["debit"]) > 0]
    rounds = sum(1 for a in amts if a >= 1000 and a % 1000 == 0)
    assert rounds / len(amts) < 0.002


def _quarter(entry_date):
    return (int(entry_date[5:7]) - 1) // 3 + 1


def test_benford_first_digit_mad_per_quarter(ds):
    je_q = {j["je_id"]: _quarter(j["entry_date"]) for j in ds.tables["journal_entries"]}
    by_q = defaultdict(list)
    for ln in ds.tables["gl_lines"]:
        amt = ln["debit"] if Decimal(ln["debit"]) > 0 else ln["credit"]
        by_q[je_q[ln["je_id"]]].append(amt)
    assert set(by_q) == {1, 2, 3, 4}
    for q, amts in by_q.items():
        mad, n = first_digit_mad(amts)
        assert n >= 5_000, (q, n)
        assert mad < 0.006, (q, mad)
