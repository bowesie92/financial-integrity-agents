"""Clean general ledger: balanced entries posted by people who stick to their own accounts,
during local business hours, with amounts that follow Benford's law."""
import math
from datetime import date

from . import config as C
from .calendar_util import business_days, month_bounds, to_utc_iso

ROLE_OF = {u: role for u, _, role, _ in C.USERS}
SITE_OF = {u: sid for u, _, _, sid in C.USERS}
TZ_OF_SITE = {sid: tz for sid, _, _, tz in C.SITES}
ACCT_NAME = {a: n for a, n, _ in C.ACCOUNTS}
ACCT_CLASS = {a: c for a, _, c in C.ACCOUNTS}

# Hours 7..18 local, busiest late morning and mid afternoon.
_HOUR_WEIGHTS = [4, 8, 10, 10, 8, 6, 8, 9, 8, 6, 4, 2]

_EXPENSES = [a for a, _, c in C.ACCOUNTS if c == "expense"
             and a not in C.RECURRING_ONLY and a not in C.SELDOM_ACCOUNTS]

# poster -> (selection weight, source)
_MANUAL = {"u01": 1.0, "u03": 2.0, "u04": 1.5, "u05": 2.0, "u06": 2.0, "u07": 2.0,
           "u08": 1.5, "u09": 1.5}
_AP = {"u10": 3.0, "u11": 3.0, "u12": 1.5, "u13": 1.5}
_SOURCE_WEIGHTS = [("manual", 0.40), ("ap_subledger", 0.38), ("system", 0.22)]

_DESC = {
    "manual": ["Adjusting entry", "Reclass between accounts", "Accrual true-up",
               "Month-end correction", "Prepaid amortization"],
    "ap_subledger": ["Vendor invoice posting", "AP batch posting", "Vendor payment posting"],
    "system": ["Inventory cost relief", "Sales batch posting", "Cash receipts batch"],
}


def build_profiles(ds):
    """For each posting user, which accounts they debit and credit, and how often."""
    rng = ds.rng("profiles")
    p = {}
    for u in list(_MANUAL) + list(_AP):
        role = ROLE_OF[u]
        if role == "ap_clerk":
            debit = ["1200", "1300", "5100"] + rng.sample(_EXPENSES, 7)
            credit = [("2000", 0.7), ("1000", 0.3)]
            weights = [1.0] * len(debit)
        else:
            k = 12 if role in ("controller", "senior_accountant") else 8
            debit = rng.sample(_EXPENSES, k) + ["1300"]
            credit = [("2100", 0.4), ("1300", 0.2), ("1000", 0.2), ("2000", 0.2)]
            weights = [1.0] * len(debit)
            if u in ("u01", "u03"):                 # the only people who touch seldom accounts
                debit += list(C.SELDOM_ACCOUNTS)
                weights += [0.04, 0.04]
            if role in ("controller", "senior_accountant"):
                debit += ["1500", "5200"]
                weights += [0.15, 0.3]
            if u == "u01":
                credit.append(("3000", 0.03))
        p[u] = {"debit": list(zip(debit, weights)), "credit": credit}
    p[C.SYSTEM_USER] = {
        "debit": [("5000", 5.0), ("1100", 3.0), ("1000", 3.0), ("5200", 0.3)],
        "credit": [("4000", 5.0), ("1200", 3.0), ("1100", 3.0), ("4100", 0.5), ("4900", 0.2)]}
    return p


def _pick(rng, pairs, exclude=None):
    items = [(a, w) for a, w in pairs if a != exclude]
    return rng.choices([a for a, _ in items], weights=[w for _, w in items])[0]


def benford_amount(rng):
    exp = rng.choices(C.DECADE_EXPONENTS, weights=C.DECADE_WEIGHTS)[0]
    return f"{(10 ** rng.random()) * 10 ** exp:.2f}"


def _approver(rng, poster, total):
    if total >= C.CFO_LIMIT:
        return C.CFO
    if total >= C.CONTROLLER_LIMIT:
        return C.CFO if poster == C.CONTROLLER else C.CONTROLLER
    if ROLE_OF[poster] in ("staff_accountant", "senior_accountant", "controller") \
            and poster != C.SYSTEM_USER:
        choices = [s for s in C.SENIORS if s != poster]
        if poster == C.CONTROLLER:
            return rng.choice(C.SENIORS)
        return rng.choice(choices)
    return None


def _day_pool():
    pools = []
    for m in range(1, 13):
        s, e = month_bounds(C.YEAR, m)
        days = business_days(s, e)
        pools.append((days, days[-3:]))
    return pools


def benford_amount_between(rng, low, high):
    """Log-uniform amount between low and high (still Benford-shaped inside that range)."""
    return f"{10 ** rng.uniform(math.log10(low), math.log10(high)):.2f}"


def make_draft(poster, day, hour, minute, second, pairs, source, desc, approver,
               tag=None, posted_day=None, memo=None):
    """One journal entry before ids are assigned. pairs = [(debit_acct, credit_acct, amount)].
    day is the entry date; posted_day (default: day) is the local date it was actually posted."""
    site = SITE_OF[poster]
    return {"day": day, "poster": poster, "source": source, "site": site, "pairs": pairs,
            "approver": approver, "desc": desc, "tag": tag, "memo": memo,
            "posted_at": to_utc_iso(posted_day or day, hour, minute, second, TZ_OF_SITE[site])}


def build_clean_gl(ds):
    rng = ds.rng("gl_clean")
    profiles = build_profiles(ds)
    ds.meta["profiles"] = profiles
    ds.meta.setdefault("drafts", [])
    pools = _day_pool()
    srcs = [s for s, _ in _SOURCE_WEIGHTS]
    src_w = [w for _, w in _SOURCE_WEIGHTS]
    for _ in range(C.N_CLEAN_JES):
        source = rng.choices(srcs, weights=src_w)[0]
        if source == "manual":
            poster = rng.choices(list(_MANUAL), weights=list(_MANUAL.values()))[0]
        elif source == "ap_subledger":
            poster = rng.choices(list(_AP), weights=list(_AP.values()))[0]
        else:
            poster = C.SYSTEM_USER
        days, month_end = pools[rng.randrange(12)]
        day = rng.choice(month_end) if rng.random() < 0.25 else rng.choice(days)
        hour = C.BUSINESS_START_HOUR + rng.choices(range(12), weights=_HOUR_WEIGHTS)[0]
        pairs = []
        for _ in range(rng.choice([1, 2])):
            d_acct = _pick(rng, profiles[poster]["debit"])
            c_acct = _pick(rng, profiles[poster]["credit"], exclude=d_acct)
            pairs.append((d_acct, c_acct, benford_amount(rng)))
        total = sum(float(a) for _, _, a in pairs)
        ds.meta["drafts"].append(make_draft(
            poster, day, hour, rng.randrange(60), rng.randrange(60), pairs, source,
            rng.choice(_DESC[source]), _approver(rng, poster, total)))


# What each tagged pattern means for scoring. Benford is one item (a whole quarter); every
# other pattern is one manifest row per journal entry.
MANIFEST_INFO = {
    "benford_violation": ("planted", "high",
        "Run the first-digit test per quarter, find 2025-Q3 nonconforming, trace it to the "
        "manual accrual entries by one user, and propose a finding."),
    "round_dollar_cluster": ("planted", "medium",
        "Flag round-dollar entries clustered at quarter end by one user in a seldom-used account."),
    "after_hours_postings": ("planted", "medium",
        "Flag a weekend or night posting, judged in the poster's local time."),
    "post_close_thin_description": ("planted", "high",
        "Flag an entry posted after the period closed, with little or no description."),
    "unusual_user_account": ("planted", "high",
        "Flag a user posting to an account they have never used, above the $5,000 floor."),
    "recurring_identical_entries": ("decoy", None,
        "Clear: identical monthly rent and payroll entries are expected."),
    "controller_month_end_weekend": ("decoy", None,
        "Clear: the controller works weekends around month end."),
    "fresno_local_hours": ("decoy", None,
        "Clear: inside Fresno's local business hours even if it looks late elsewhere."),
    "post_close_cfo_approved": ("decoy", None,
        "Clear: post-close adjustment with a full description and documented CFO approval."),
}
_GROUPED = {"benford_violation"}


def finalize_gl(ds):
    """Sort all drafts by posting time, assign ids, write journal entries and lines, and
    build the ground-truth manifest."""
    drafts = sorted(ds.meta["drafts"], key=lambda d: d["posted_at"])
    grouped = {}
    for i, d in enumerate(drafts, start=1):
        je_id = f"JE-{C.YEAR}-{i:06d}"
        ds.tables["journal_entries"].append({
            "je_id": je_id, "period_id": d["day"].strftime("%Y-%m"),
            "entry_date": d["day"].isoformat(), "posted_at": d["posted_at"],
            "posted_by": d["poster"], "approved_by": d["approver"], "source": d["source"],
            "description": d["desc"], "site_id": d["site"]})
        for k, (d_acct, c_acct, amt) in enumerate(d["pairs"]):
            memo = d["memo"] if (d["memo"] and k == 0) else ACCT_NAME[d_acct]
            ds.tables["gl_lines"].append({"je_id": je_id, "account_id": d_acct,
                                          "site_id": d["site"], "debit": amt, "credit": "0.00",
                                          "memo": memo})
            ds.tables["gl_lines"].append({"je_id": je_id, "account_id": c_acct,
                                          "site_id": d["site"], "debit": "0.00", "credit": amt,
                                          "memo": None})
        if d["tag"]:
            if d["tag"] in _GROUPED:
                grouped.setdefault(d["tag"], []).append(je_id)
            else:
                _manifest(ds, d["tag"], {"je_ids": [je_id]})
    for tag, ids in grouped.items():
        _manifest(ds, tag, {"je_ids": ids, "quarter": "2025-Q3"})


def _manifest(ds, tag, refs):
    kind, severity, expected = MANIFEST_INFO[tag]
    ds.manifest.append({"kind": kind, "agent": "gl_sentinel", "pattern": tag,
                        "severity": severity, "expected_behavior": expected,
                        "record_refs": refs})
