# Phase 4 amendments to docs/tools.md

Recorded 2026-10-05 while building the tool layer (task 4.3). docs/tools.md stays the design
record; where the code differs, this file is the reason and the code is the rule.

1. **Output budget covers the whole envelope.** Principle 6 says 6,000 characters of JSON. The
   limit applies to the entire envelope the model receives, so the result is cut at 5,600
   characters to leave room for `ok`, `row_count`, `truncated` and `notes`. Rows are dropped one
   at a time, so as many as fit are kept.
2. **`get_records` shows lines inline.** Journal entries show up to 20 gl lines and invoices show
   their invoice lines, so one call gives the whole record. Vendor name and address are labeled
   untrusted.
3. **`propose_finding` requires `cause` and `effect`.** The model may write "Not determinable
   from the data". Evidence items are `{table, id, note?}` and every item is checked for
   existence before the insert. A dry-run flag on the tool context rolls the insert back, for tests.
4. **`round_dollar_scan`:** `min_amount` here is the smallest round amount that counts (default
   1,000) and does not filter the population, because the shared filter would otherwise make
   every share meaningless. Results show round entries and round lines, since each entry has a
   debit line and a credit line.
5. **`timing_scan` rule definitions.** weekend and holiday use the poster's local date;
   after_hours is any local time outside 07:00 to 19:00; post_close is a local posting date after
   the period's close date; last_3_days_of_period is a posting date within the last three
   calendar days of the entry's period. Entry-level filters (`account_class`, `min_amount`) match
   entries that have at least one qualifying line.
6. **`user_account_profile` gained a role-peer comparison and an optional `period_id`.** Reason:
   the planted unusual-posting pattern (an AP clerk posting to fixed assets from the first
   month) can never look "new" under a six-month lookback, so the spec's tool could not surface
   it. The tool now also lists accounts the user posts to that no one else in the same role
   posts to, rarest first, with the share of the user's lines. With `period_id` it also lists the
   period's lines on classes and on accounts not used in the prior six periods. Without
   `period_id` it profiles the whole year and lists nothing as new.
7. **`list_journal_entries` needs at least one filter**, so an aimless call cannot sample the
   first 50 entries by accident. `min_amount` applies to the entry's total debits.
8. **Benford populations** use GL lines with an amount of at least $1.00. Bands are Nigrini's
   published MAD ranges (below 0.006 close, to 0.012 acceptable, to 0.015 marginal, above 0.015
   nonconforming). The 5,000-record floor applies to both the first-digit and first-two-digit tests.
9. **`vendor_profile`: `matches_employee_address` is always null.** The dataset holds no employee
   addresses, so the check cannot be run. The result says so rather than guessing. The PO box flag
   is a text match on the vendor address.
10. **`find_duplicate_invoices`.** Both modes pair invoices from one vendor within `window_days`.
    exact: same document number (ignoring case) and same amount. near: same document number with
    an amount within the tolerance (percent of the larger amount), or the same amount with a variant
    document number (hyphens or zero padding ignored), or the same amount with a different document
    number. Each pair says which, and whether each invoice was paid. The third type will also
    return a vendor that legitimately bills a flat amount every month; clearing that is the
    agent's job.
11. **`find_split_groups`.** Invoices under `limit_amount` are grouped per vendor, greedily: a group
    is every invoice within `window_days` of its first invoice. A group needs at least two
    invoices and a sum at or above the limit. It lists who entered and approved them. A stray pair
    that happens to cross the limit can appear; the amounts show whether it is "just under".
12. **`po_match_check`** compares the sum of all invoices on a PO with the PO amount (invoice totals
    include tax). It also lists invoices whose PO belongs to another vendor, because the manifest
    expects that to be flagged, and summarizes invoices with no PO (count, total, largest 15)
    instead of listing all of them.
13. **`bank_change_payments`** joins a change to payments on that vendor's invoices made on or
    after the change and within `within_days`. `paid_to_new_account` is null for checks, which
    carry no bank digits.
14. **`amount_outliers`** is upward only and compares each invoice with the same vendor's earlier
    invoices (sample standard deviation). It will also flag some ordinary vendors with a wide
    range at z of 3 to 5; the rules-only baseline sees exactly the same list.
15. **`new_vendor_large_invoices`**: vendor age is invoice date minus the vendor's creation date.
    Every invoice in this data carries an approver, so "approval present" is always true; the
    tool therefore also shows the approver's role and the approver the amount required.

## Amendment for task 4.8 (2026-10-06)

16. **`cross_state_invoices` (new tool, decision D26).** D24 scores one state-rule decision, use tax on
    cross-state purchases, but no tool in docs/tools.md could find a cross-state invoice: the agent would
    have had to open all 120 vendors one by one, so the scored pass ("flags it, names the destination
    state, cites get_regulation, estimates the use tax") was unreachable. The tool lists invoices whose
    vendor state differs from the receiving site's state, with the taxable-line and resale-line totals, the
    tax the vendor charged, and the tax at the destination state's base rate on the taxable lines (computed
    in code, per D6, from the same `reference/regulations.json` row that `get_regulation` cites). It states
    facts and an estimate only. It does not say which invoices are exposed: telling a taxed invoice or a
    resale purchase from an untaxed supply purchase is still the agent's judgment. 12 invoices per call,
    `offset` for the next page, so every page fits the 6,000 character envelope. The rules-only baseline is
    unchanged (D25): it still has no use-tax rule.
17. **Wording guard extended to AP.** A recommendation that advises stopping, holding, blocking,
    cancelling, recalling, freezing, suspending or recovering a payment, a vendor or an invoice is rejected,
    the same way advice to reverse or void a journal entry is (memo rule 3, enforced where the text is
    written). The rejection message says what to change.
18. **One run script for both agents.** `scripts/run_review.py --agent gl|ap`; `scripts/run_gl_sentinel.py`
    still works and calls it with `--agent gl`. The memo heading names the agent.
