"""Planted GL patterns (what the agent must find) and decoys (what it must clear)."""
from datetime import date, timedelta

from . import config as C
from .calendar_util import business_days, is_business_day, month_bounds, nth_business_day_after
from .gl_clean import (ACCT_CLASS, _DESC, _HOUR_WEIGHTS, _approver, benford_amount,
                       benford_amount_between, make_draft)

# Fabricated amounts lean on first digits 5 to 9, the way invented numbers tend to.
_FAB_DIGITS = [1, 2, 3, 4, 5, 6, 7, 8, 9]
_FAB_WEIGHTS = [0.02, 0.02, 0.03, 0.05, 0.14, 0.20, 0.24, 0.20, 0.10]
N_FAB_ENTRIES, FAB_PAIRS = 380, 3


def _hour(rng):
    return C.BUSINESS_START_HOUR + rng.choices(range(12), weights=_HOUR_WEIGHTS)[0]


def _expense_debits(ds, user):
    return [a for a, _ in ds.meta["profiles"][user]["debit"] if ACCT_CLASS[a] == "expense"]


def _days(start_month, end_month):
    out = []
    for m in range(start_month, end_month + 1):
        out += business_days(*month_bounds(C.YEAR, m))
    return out


def _fab_amount(rng):
    digit = rng.choices(_FAB_DIGITS, weights=_FAB_WEIGHTS)[0]
    exp = rng.choices([1, 2, 3], weights=[0.25, 0.45, 0.30])[0]
    return f"{(digit + rng.random()) * 10 ** exp:.2f}"


def add_planted(ds):
    rng = ds.rng("gl_planted")
    drafts = ds.meta["drafts"]

    # 1. Benford violation: fabricated manual accruals by u06 in Q3.
    q3 = _days(7, 9)
    exp_accts = _expense_debits(ds, "u06")
    for _ in range(N_FAB_ENTRIES):
        pairs = [(rng.choice(exp_accts), "2100", _fab_amount(rng)) for _ in range(FAB_PAIRS)]
        total = sum(float(a) for _, _, a in pairs)
        drafts.append(make_draft("u06", rng.choice(q3), _hour(rng), rng.randrange(60),
                                 rng.randrange(60), pairs, "manual",
                                 rng.choice(_DESC["manual"]),
                                 _approver(rng, "u06", total), tag="benford_violation"))

    # 2. Round-dollar cluster: u03, last two business days of each quarter end, account 6960.
    for month in (3, 6, 9, 12):
        last_two = business_days(*month_bounds(C.YEAR, month))[-2:]
        for _ in range(15):
            amt = f"{1000 * rng.randint(2, 24):.2f}"
            drafts.append(make_draft("u03", rng.choice(last_two), _hour(rng), rng.randrange(60),
                                     rng.randrange(60), [("6960", "2100", amt)], "manual",
                                     rng.choice(_DESC["manual"]), _approver(rng, "u03", float(amt)),
                                     tag="round_dollar_cluster"))

    # 3. Weekend and after-hours postings by u05 (Phoenix), July to December, local time.
    weekends, weeknights = [], []
    d = date(C.YEAR, 7, 1)
    while d <= date(C.YEAR, 12, 31):
        if d.day <= 20 and d not in C.HOLIDAYS:
            (weekends if d.weekday() >= 5 else weeknights).append(d)
        d += timedelta(days=1)
    for k in range(40):
        if k < 20:
            day, hour = rng.choice(weekends), rng.randint(9, 16)
        else:
            day, hour = rng.choice(weeknights), rng.choice([21, 22, 23, 0, 1, 2, 3, 4])
        acct = rng.choice(_expense_debits(ds, "u05"))
        amt = benford_amount(rng)
        drafts.append(make_draft("u05", day, hour, rng.randrange(60), rng.randrange(60),
                                 [(acct, "2100", amt)], "manual", rng.choice(_DESC["manual"]),
                                 _approver(rng, "u05", float(amt)), tag="after_hours_postings"))

    # 4. Post-close entries, thin or no description: u07 (15) and u08 (10), periods Jun to Dec.
    close = {int(p["period_id"][5:]): date.fromisoformat(p["close_date"])
             for p in ds.tables["periods"] if p["period_id"].startswith(str(C.YEAR))}
    thin = [None] * 15 + rng.sample(["adj", "fix", "per JM", "corr", "reclass"] * 2, 10)
    for k, desc in enumerate(thin):
        user = "u07" if k < 15 else "u08"
        month = rng.randint(6, 12)
        posted_day = nth_business_day_after(close[month], rng.randint(2, 12))
        acct = rng.choice(_expense_debits(ds, user))
        amt = benford_amount_between(rng, 10, 4999)
        drafts.append(make_draft(user, rng.choice(business_days(*month_bounds(C.YEAR, month))),
                                 _hour(rng), rng.randrange(60), rng.randrange(60),
                                 [(acct, "2100", amt)], "manual", desc, None,
                                 tag="post_close_thin_description", posted_day=posted_day))

    # 5. Unusual user-account pairing: AP clerk u11 debits Fixed assets (1500), $5,000 and up.
    days = _days(1, 12)
    for _ in range(15):
        amt = benford_amount_between(rng, 5_000, 60_000)
        credit = rng.choice(["2000", "1000"])
        drafts.append(make_draft("u11", rng.choice(days), _hour(rng), rng.randrange(60),
                                 rng.randrange(60), [("1500", credit, amt)], "ap_subledger",
                                 rng.choice(_DESC["ap_subledger"]), _approver(rng, "u11", float(amt)),
                                 tag="unusual_user_account"))


def _pay_date(year, month, day):
    d = date(year, month, min(day, month_bounds(year, month)[1].day))
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d


def add_decoys(ds):
    rng = ds.rng("gl_decoys")
    drafts = ds.meta["drafts"]

    # Identical monthly rent (system schedule, controller approves) and semi-monthly payroll
    # (system, CFO).
    for month in range(1, 13):
        first = business_days(*month_bounds(C.YEAR, month))[0]
        drafts.append(make_draft(C.SYSTEM_USER, first, 9, 15, 0, [("6100", "1000", "18000.00")],
                                 "system", "Monthly rent, Phoenix HQ and warehouse",
                                 C.CONTROLLER, tag="recurring_identical_entries"))
        for day in (15, 31):
            drafts.append(make_draft(
                C.SYSTEM_USER, _pay_date(C.YEAR, month, day), 8, 0, 0,
                [("6000", "1000", "61250.00"), ("6010", "2200", "4685.63"),
                 ("6020", "1000", "7420.00")],
                "payroll", "Payroll run", C.CFO, tag="recurring_identical_entries"))

    # Controller posts on weekends near month end (8 months).
    for month in sorted(rng.sample(range(1, 13), 8)):
        end = month_bounds(C.YEAR, month)[1]
        cands = [end - timedelta(days=k) for k in range(7)]
        day = rng.choice([c for c in cands if c.weekday() >= 5 and c not in C.HOLIDAYS])
        amt = benford_amount(rng)
        acct = rng.choice(_expense_debits(ds, "u01"))
        drafts.append(make_draft("u01", day, rng.randint(8, 16), rng.randrange(60),
                                 rng.randrange(60), [(acct, "2100", amt)], "manual",
                                 rng.choice(_DESC["manual"]), _approver(rng, "u01", float(amt)),
                                 tag="controller_month_end_weekend"))

    # Fresno staff accountant u09 posts at 18:xx local, four of them on Fridays. In UTC or
    # Phoenix time some of these look like nights or weekends.
    fridays = [d for d in _days(1, 12) if d.weekday() == 4]
    others = [d for d in _days(1, 12) if d.weekday() < 4]
    for day in rng.sample(fridays, 4) + rng.sample(others, 6):
        amt = benford_amount(rng)
        acct = rng.choice(_expense_debits(ds, "u09"))
        drafts.append(make_draft("u09", day, 18, rng.randint(5, 55), rng.randrange(60),
                                 [(acct, "2100", amt)], "manual", rng.choice(_DESC["manual"]),
                                 _approver(rng, "u09", float(amt)), tag="fresno_local_hours"))

    # One post-close adjustment with a full description and documented CFO approval.
    sept_close = date.fromisoformat(
        next(p["close_date"] for p in ds.tables["periods"] if p["period_id"] == "2025-09"))
    note = ("Post-close adjustment per CFO memo AA-2025-014: inventory count variance, "
            "approved by M. Chen 2025-10-20")
    drafts.append(make_draft("u01", date(2025, 9, 29), 10, 30, 0,
                             [("5200", "2100", "31862.40")], "manual", note, C.CFO,
                             tag="post_close_cfo_approved",
                             posted_day=nth_business_day_after(sept_close, 10), memo=note))
