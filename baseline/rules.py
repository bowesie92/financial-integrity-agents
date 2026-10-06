"""Rules-only baseline (task 4.5). Twelve fixed rules, one per line of docs/metrics.md section 5,
written before any agent exists. No LLM. Thresholds live in THRESHOLDS_V1 (as written in Phase 1) and
THRESHOLDS_V2 (V1 plus the dated Amendment 1 in docs/metrics.md); both are pinned by tests, and both
are reported. A number changes only through an entry under Amendments in docs/metrics.md.

Each rule returns findings shaped {rule, agent, refs, detail}. refs holds je_ids or invoice_ids
(and payment_ids) so the evaluation harness can match a finding to a manifest row by overlap.
The baseline reuses the tool query functions where their meaning equals the metrics wording and
runs its own SQL where it does not (see docs/baseline_notes.md).
"""
from collections import defaultdict

from fia_tools import analytics as A
from fia_tools import ap as AP
from fia_tools import gl as GL
from fia_tools.db import query

THRESHOLDS_V1 = {
    "benford_mad_above": 0.015,
    "round_min_amount": 1000, "round_multiple": 1000, "round_min_entries_per_month": 20,
    "post_close": True,
    "pairing_rule": "unused_class", "pairing_min_amount": 5000, "pairing_history_periods": 6,
    "pairing_max_user_share": None,
    "exact_window_days": 30,
    "near_window_days": 30, "near_tolerance_pct": 1,
    "split_window_days": 7, "split_limit": 5000,
    "new_vendor_max_age_days": 29, "new_vendor_min_amount": 5000,      # "under 30 days"
    "po_excess_pct": 5, "po_excess_dollars": 100,
    "outlier_z": 3, "outlier_min_prior": 6,
    "bank_change_within_days": 30, "bank_change_min_payment": 5000,
}
# Amendment 1 (2026-10-05, before any agent run): two rules that cannot fire on this data as first written.
#  - round-dollar: 5 entries a month instead of 20. Ordinary users post at most one round entry a month;
#    the Phase 1 figure of 20 was a blind guess.
#  - user-account pairing: the D20 rule (no role peer ever posts to the account and the user's share of
#    entries is under 1 percent) instead of "class unused for 6 months"; D20 already replaced the wording.
#    Automated sources (system, payroll) are skipped, as the Phase 2 data hygiene note intends.
THRESHOLDS_V2 = {**THRESHOLDS_V1, "round_min_entries_per_month": 5,
                 "pairing_rule": "peer_rarity", "pairing_max_user_share": 0.01}
VERSIONS = {"v1": THRESHOLDS_V1, "v2": THRESHOLDS_V2}
T = THRESHOLDS_V1       # rules read the active thresholds from here; use_version() switches them
GL_RULES = ("benford", "round_dollar", "timing", "post_close", "user_account_pairing")
AP_RULES = ("exact_duplicate", "near_duplicate", "split", "new_vendor", "po_mismatch", "outlier", "bank_change")
ALL_RULES = GL_RULES + AP_RULES


def use_version(version):
    """Make `version` (v1 or v2) the active thresholds. Returns the dict."""
    global T
    T = VERSIONS[version]
    return T


def _finding(rule, agent, refs, **detail):
    return {"rule": rule, "agent": agent, "refs": refs, "detail": detail}


def _fixed(out, key):
    """The tool functions cap output at 50 rows. The baseline must not silently drop findings."""
    if out.get(key):
        raise RuntimeError(f"baseline needs paging: tool output was truncated ({key})")


# ---- GL --------------------------------------------------------------------------------------
def benford(ctx):
    out = []
    for q in ("2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"):
        st = A.first_digit_stats(GL._digit_counts(ctx, {"quarter": q}, 1))
        if st["mad"] is not None and st["mad"] > T["benford_mad_above"]:
            out.append(_finding("benford", "gl_sentinel", {"quarter": q}, mad=st["mad"], band=st["band"],
                                records=st["n"], sufficient_sample=st["sufficient_sample"]))
    return out


def round_dollar(ctx):
    rows = query(ctx.conn, """
        select je.posted_by, je.period_id, array_agg(distinct je.je_id order by je.je_id) as je_ids
        from fia.journal_entries je join fia.gl_lines l on l.je_id = je.je_id
        where greatest(l.debit, l.credit) >= %s and mod(greatest(l.debit, l.credit), %s) = 0
        group by 1, 2 having count(distinct je.je_id) >= %s order by 1, 2""",
                 [T["round_min_amount"], T["round_multiple"], T["round_min_entries_per_month"]])
    return [_finding("round_dollar", "gl_sentinel", {"je_ids": r["je_ids"]}, user=r["posted_by"],
                     period=r["period_id"], round_entries=len(r["je_ids"])) for r in rows]


def _timing_rows(ctx):
    return query(ctx.conn, f"""
        select je.je_id, je.posted_by, je.posted_at, coalesce(s.timezone, 'America/Phoenix') as tz,
               pe.end_date, pe.close_date
        from {GL.JE_FROM} order by je.posted_at, je.je_id""")


def timing_and_post_close(ctx):
    timing, post = [], []
    for r in _timing_rows(ctx):
        flags = A.timing_flags(r["posted_at"], r["tz"], r["end_date"], r["close_date"])
        hit = [f for f in flags if f in ("weekend", "holiday", "after_hours")]
        if hit:
            timing.append(_finding("timing", "gl_sentinel", {"je_ids": [r["je_id"]]}, user=r["posted_by"],
                                   flags=hit))
        if "post_close" in flags:
            post.append(_finding("post_close", "gl_sentinel", {"je_ids": [r["je_id"]]}, user=r["posted_by"]))
    return timing, post


def user_account_pairing(ctx):
    if T["pairing_rule"] == "peer_rarity":
        return _pairing_peer_rarity(ctx)
    return _pairing_unused_class(ctx)


def _pairing_peer_rarity(ctx):
    """D20: a line of at least $5,000 in an account that no other user in the poster's role ever posts to,
    where the poster's own entries to it are under 1 percent of all the poster's entries. Entries from the
    automated sources (system, payroll) are skipped: they are not a person choosing an account."""
    rows = query(ctx.conn, """
        with ue as (select je.posted_by, l.account_id, count(distinct je.je_id) as n
                    from fia.gl_lines l join fia.journal_entries je on je.je_id = l.je_id group by 1, 2),
             ut as (select posted_by, count(*) as t from fia.journal_entries group by 1)
        select je.je_id, je.posted_by, je.period_id, l.account_id, greatest(l.debit, l.credit) as amount,
               ue.n as account_entries, ut.t as user_entries
        from fia.gl_lines l join fia.journal_entries je on je.je_id = l.je_id
             join ue on ue.posted_by = je.posted_by and ue.account_id = l.account_id
             join ut on ut.posted_by = je.posted_by
             join fia.users u on u.user_id = je.posted_by
        where greatest(l.debit, l.credit) >= %s and ue.n::numeric / ut.t < %s
          and je.source not in ('system', 'payroll')
          and not exists (select 1 from ue ue2 join fia.users u2 on u2.user_id = ue2.posted_by
                          where ue2.account_id = l.account_id and u2.role = u.role
                                and ue2.posted_by <> je.posted_by)
        order by je.je_id, l.account_id""", [T["pairing_min_amount"], T["pairing_max_user_share"]])
    by = defaultdict(list)
    for r in rows:
        by[r["je_id"]].append(r)
    return [_finding("user_account_pairing", "gl_sentinel", {"je_ids": [je]}, user=v[0]["posted_by"],
                     period=v[0]["period_id"],
                     lines=[{"account_id": r["account_id"], "amount": r["amount"],
                             "user_share": round(r["account_entries"] / r["user_entries"], 4)} for r in v])
            for je, v in sorted(by.items())]


def _pairing_unused_class(ctx):
    """A line of at least $5,000 in an account class the user did not touch in the prior 6 periods.
    The user must have posted something in that window, otherwise there is no history to compare."""
    lo = "to_char(to_date(x.period_id, 'YYYY-MM') - make_interval(months => %s), 'YYYY-MM')"
    rows = query(ctx.conn, f"""
        with u as (select distinct je.posted_by, a.account_class, je.period_id
                   from fia.gl_lines l join fia.journal_entries je on je.je_id = l.je_id
                        join fia.accounts a on a.account_id = l.account_id),
             x as (select je.je_id, je.posted_by, je.period_id, l.account_id, a.account_class,
                          greatest(l.debit, l.credit) as amount
                   from fia.gl_lines l join fia.journal_entries je on je.je_id = l.je_id
                        join fia.accounts a on a.account_id = l.account_id
                   where greatest(l.debit, l.credit) >= %s)
        select x.je_id, x.posted_by, x.period_id, x.account_id, x.account_class, x.amount
        from x
        where exists (select 1 from u where u.posted_by = x.posted_by and u.period_id < x.period_id
                      and u.period_id >= {lo})
          and not exists (select 1 from u where u.posted_by = x.posted_by and u.account_class = x.account_class
                          and u.period_id < x.period_id and u.period_id >= {lo})
        order by x.je_id, x.account_id""", [T["pairing_min_amount"], T["pairing_history_periods"],
                                           T["pairing_history_periods"]])
    by = defaultdict(list)
    for r in rows:
        by[r["je_id"]].append(r)
    return [_finding("user_account_pairing", "gl_sentinel", {"je_ids": [je]}, user=v[0]["posted_by"],
                     period=v[0]["period_id"], lines=[{"account_id": r["account_id"], "account_class": r["account_class"],
                                                      "amount": r["amount"]} for r in v])
            for je, v in sorted(by.items())]


# ---- AP --------------------------------------------------------------------------------------
def duplicates(ctx):
    """Exact: same vendor and same invoice number (any dates), or same vendor, same amount and dates
    within 30 days. Near: same vendor, amounts within 1 percent, dates within 30 days, and not already
    exact. Document numbers are compared as typed, ignoring case and outer spaces."""
    pairs = query(ctx.conn, """
        select a.vendor_id, a.invoice_id as a_id, b.invoice_id as b_id, a.doc_number as a_doc, b.doc_number as b_doc,
               a.txn_date as a_date, b.txn_date as b_date, a.total_amt as a_amt, b.total_amt as b_amt,
               (upper(btrim(a.doc_number)) = upper(btrim(b.doc_number))) as same_doc,
               (a.total_amt = b.total_amt and b.txn_date - a.txn_date <= %s) as same_amount_close,
               (abs(a.total_amt - b.total_amt) <= greatest(a.total_amt, b.total_amt) * %s / 100.0
                and b.txn_date - a.txn_date <= %s) as near
        from fia.invoices a join fia.invoices b on b.vendor_id = a.vendor_id
             and (b.txn_date, b.invoice_id) > (a.txn_date, a.invoice_id)
        where upper(btrim(a.doc_number)) = upper(btrim(b.doc_number))
           or b.txn_date - a.txn_date <= greatest(%s, %s)
        order by a.txn_date, a.invoice_id, b.invoice_id""",
                  [T["exact_window_days"], T["near_tolerance_pct"], T["near_window_days"],
                   T["exact_window_days"], T["near_window_days"]])
    exact, near = [], []
    for p in pairs:
        refs = {"invoice_ids": [p["a_id"], p["b_id"]]}
        d = {"vendor_id": p["vendor_id"], "docs": [p["a_doc"], p["b_doc"]], "amounts": [p["a_amt"], p["b_amt"]],
             "dates": [p["a_date"], p["b_date"]]}
        if p["same_doc"] or p["same_amount_close"]:
            exact.append(_finding("exact_duplicate", "ap_guardian", refs, **d))
        elif p["near"]:
            near.append(_finding("near_duplicate", "ap_guardian", refs, **d))
    return exact, near


def split(ctx):
    out = AP.find_split_groups(ctx, {"window_days": T["split_window_days"], "limit_amount": T["split_limit"]})
    return [_finding("split", "ap_guardian", {"invoice_ids": g["invoice_ids"]}, vendor_id=g["vendor_id"],
                     amounts=g["amounts"], total=g["sum"]) for g in out["rows"]]


def new_vendor(ctx):
    out = AP.new_vendor_large_invoices(ctx, {"max_vendor_age_days": T["new_vendor_max_age_days"],
                                             "min_amount": T["new_vendor_min_amount"]})
    _fixed(out, "more_available")
    return [_finding("new_vendor", "ap_guardian", {"invoice_ids": [r["invoice_id"]]}, vendor_id=r["vendor_id"],
                     amount=r["total_amt"], vendor_age_days=r["vendor_age_days"]) for r in out["rows"]]


def po_mismatch(ctx):
    """Per invoice: total above its own PO by more than 5 percent and by more than $100."""
    rows = query(ctx.conn, """
        select i.invoice_id, i.vendor_id, po.vendor_id as po_vendor, po.po_id, i.total_amt, po.amount
        from fia.invoices i join fia.purchase_orders po on po.po_id = i.po_id
        where i.total_amt - po.amount > %s and i.total_amt > po.amount * (1 + %s / 100.0)
        order by i.invoice_id""", [T["po_excess_dollars"], T["po_excess_pct"]])
    return [_finding("po_mismatch", "ap_guardian", {"invoice_ids": [r["invoice_id"]]}, vendor_id=r["vendor_id"],
                     po_id=r["po_id"], invoice_amount=r["total_amt"], po_amount=r["amount"],
                     po_vendor_differs=r["po_vendor"] != r["vendor_id"]) for r in rows]


def outlier(ctx):
    out = AP.amount_outliers(ctx, {"min_prior_invoices": T["outlier_min_prior"], "z_threshold": T["outlier_z"]})
    _fixed(out, "more_available")
    return [_finding("outlier", "ap_guardian", {"invoice_ids": [r["invoice_id"]]}, vendor_id=r["vendor_id"],
                     amount=r["total_amt"], z=r["z"], prior_n=r["prior_n"]) for r in out["rows"]]


def bank_change(ctx):
    out = AP.bank_change_payments(ctx, {"within_days": T["bank_change_within_days"],
                                        "min_payment": T["bank_change_min_payment"]})
    _fixed(out, "more_available")
    return [_finding("bank_change", "ap_guardian",
                     {"invoice_ids": [r["invoice_id"]], "payment_ids": [r["payment_id"]]}, vendor_id=r["vendor_id"],
                     payment_amount=r["payment_amount"], days_after_change=r["days_after_change"],
                     verified=r["verified"]) for r in out["rows"]]


def run_all(ctx):
    """Every rule, in a fixed order. Deterministic: the same data gives the same list."""
    timing, post = timing_and_post_close(ctx)
    exact, near = duplicates(ctx)
    return (benford(ctx) + round_dollar(ctx) + timing + post + user_account_pairing(ctx)
            + exact + near + split(ctx) + new_vendor(ctx) + po_mismatch(ctx) + outlier(ctx) + bank_change(ctx))
