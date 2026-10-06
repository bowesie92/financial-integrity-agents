# Rules-only baseline notes (task 4.5)

The baseline is the twelve fixed rules in `docs/metrics.md` section 5, written before any agent
exists. Code: `baseline/rules.py` (thresholds in `THRESHOLDS_V1` and `THRESHOLDS_V2`, both pinned by
tests). Run: `python -m baseline.run --version v1|v2`. Score: `python -m baseline.score` (admin role,
reads the ground truth). No model calls, no cost, nothing written to the database. Task 4.9 builds
the full evaluation harness; the arithmetic is the same.

## Two versions, both reported
- **v1** is the thresholds as written in Phase 1. It is the pre-registered baseline.
- **v2** is v1 plus Amendment 1 (docs/metrics.md): round-dollar needs 5 entries a month instead of 20,
  and user-account pairing uses the D20 peer and rarity rule instead of "class unused for 6 months".
  Reason: on seed 1, v1 cannot fire on either rule (the planted round-dollar cluster is 15 entries in
  each quarter-end month, and the planted user posts to the asset class in most months).
- v2 is not blind: the author had seen the planted counts. That is why v1 stays in every table.

## How each rule is built
Reuses a tool query: split, new vendor, outlier, bank change (and the Benford digit counts, timing
flags and first-digit statistics in `fia_tools/analytics.py`). Own SQL because the metrics wording
differs from the tool: round-dollar, exact and near duplicate, PO mismatch, user-account pairing.

## Readings I chose (each could be read another way)
1. **Benford** runs on all GL lines of at least $1 per quarter, not expense-only lines (D19).
2. **Round-dollar** counts distinct entries per user per period with at least one line of $1,000 or
   more that is an exact multiple of $1,000.
3. **Timing** flags weekend, US federal holiday or outside 07:00 to 19:00 in the poster's local time.
   **Post-close** is its own rule and uses the posting time, not the accounting date, because the
   accounting date always sits inside the period.
4. **User-account pairing, v1**: a line of $5,000 or more in an account class the user did not touch in
   the prior 6 periods; a user with no postings in that window is not flagged. **v2**: a line of $5,000
   or more in an account no other user in the poster's role ever posts to, where the poster's own
   entries to it are under 1 percent of the poster's entries; system and payroll entries are skipped.
5. **Exact duplicate**: same vendor and same invoice number (ignoring case and outer spaces) on any
   dates, or same vendor and same amount within 30 days. **Near duplicate**: amounts within 1 percent
   within 30 days and not already exact.
6. **PO mismatch** compares each invoice with its own PO (more than 5 percent and more than $100). It
   does not add up several invoices on one PO and it does not check that the PO belongs to the vendor,
   because the metrics list has no such rule. That is why 3 wrong-vendor PO items are missed.
7. **New vendor** uses "under 30 days", so a vendor age of 0 to 29 days.
8. **Bank change** flags any payment of $5,000 or more within 30 days after any bank-detail change,
   verified or not. The baseline has no use-tax rule and no prompt-injection handling.

## What the baseline does on seed 1 (0 model calls)
| | v1 | v2 |
| --- | --- | --- |
| Findings | 177 | 197 |
| Planted recall | 0.54 | 0.94 |
| Planted recall where a rule exists | 0.56 | 0.98 |
| Decoy clearance | 0.83 | 0.83 |

- The v2 baseline finds nearly every planted item that a plain rule can express. What it cannot do is
  tell a decoy from a real anomaly: controller month-end weekends, the fixed monthly vendor, the large
  first invoice with a PO, the CFO-approved post-close entry and the verified bank change are all
  flagged. It also has no use-tax rule, no wrong-vendor PO check and no injection handling.
  So the agent's case rests on decoy clearance, use tax and red-team handling, not on recall.
- Precision is low where a rule is broad: near duplicate 0.08, outlier 0.26 (ordinary wide-range
  vendors), exact duplicate 0.63 (a fixed monthly vendor and a same-amount decoy).

## Freeze
`docs/metrics.md` says no threshold changes after agent results exist. None exist yet. A change before
then goes under Amendments there with a reason; after that it needs a new set of runs.
