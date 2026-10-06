# Rules-only baseline notes (task 4.5)

The baseline is the twelve fixed rules in `docs/metrics.md` section 5, written before any agent
exists. Code: `baseline/rules.py` (thresholds in `THRESHOLDS`, pinned by a test), run with
`python -m baseline.run`, scored with `python -m baseline.score` (needs the admin role, reads the
ground truth). It makes no model calls, costs nothing and writes nothing to the database.
Task 4.9 builds the full evaluation harness; the arithmetic here is the same.

## How each rule is built
Reuses a tool query: split, new vendor, outlier, bank change (and the Benford digit counts, timing
flags and first-digit statistics in `fia_tools/analytics.py`). Own SQL because the metrics wording
differs from the tool: round-dollar, exact and near duplicate, PO mismatch, user-account pairing.

## Readings I chose (each could be read another way)
1. **Benford** runs on all GL lines of at least $1 per quarter, not expense-only lines. The Phase 2
   amendment moved the population because expense-only quarters fall under the 5,000-record floor.
2. **Round-dollar** counts distinct entries per user per period that have at least one line of
   $1,000 or more that is an exact multiple of $1,000.
3. **Timing** flags weekend, US federal holiday or outside 07:00 to 19:00 in the poster's local time.
   **Post-close** is its own rule and uses the posting time, not the accounting date, because the
   accounting date always sits inside the period.
4. **User-account pairing** follows the metrics wording: a line of $5,000 or more in an account class
   the user did not touch in the prior 6 periods. A user with no postings in that window is not
   flagged, because there is nothing to compare with. This is the metrics rule, not the Phase 2
   amendment (no peer ever posts to the account and the user's share is under 1 percent).
5. **Exact duplicate**: same vendor and same invoice number (ignoring case and outer spaces) on any
   dates, or same vendor and same amount within 30 days. **Near duplicate**: amounts within 1 percent
   within 30 days and not already exact.
6. **PO mismatch** compares each invoice with its own PO (more than 5 percent and more than $100). It
   does not add up several invoices on one PO and it does not check that the PO belongs to the vendor.
7. **New vendor** uses "under 30 days", so a vendor age of 0 to 29 days.
8. **Bank change** flags any payment of $5,000 or more within 30 days after any bank-detail change,
   verified or not. The baseline has no use-tax rule and no prompt-injection handling.

## What the baseline does on seed 1 (177 findings, 0 model calls)
Planted recall is 0.54 overall and decoy clearance is 0.83. Both are expected to change only through
the agents, not through edits here.
- **Two planted GL patterns are never flagged, by construction of the fixed thresholds.** The planted
  round-dollar cluster is 15 entries in each quarter-end month, and the rule needs 20. The planted
  unusual-account user (u11) posts to the asset class in most months, so a class unused for 6
  months never occurs after the first entry, which has no history.
- Precision is low where a rule is broad: near duplicate 0.08, outlier 0.26 (ordinary wide-range
  vendors), exact duplicate 0.63 (a fixed monthly vendor and a same-amount decoy).
- Every decoy a plain rule cannot know about is flagged: controller weekends, the fixed monthly
  vendor, the large first invoice with a PO, the CFO-approved post-close entry, the verified bank
  change.

## Freeze
`docs/metrics.md` says no threshold changes after agent results exist. None exist yet. Any change
before then goes under Amendments there with a reason; after that it needs a new set of runs.
