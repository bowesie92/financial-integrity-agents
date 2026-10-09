# GL Sentinel review gl-20261009-214329-6cd1a5

Status: finished. Model calls: 23. Tool calls: 70. Findings proposed: 8. Tokens in/out: 1723296/29605. Cost: $0.9199. Time: 247.97 s.
Model alias: demo-plus. Prompt version: gl-7. Findings read from the database.

Every item below is a proposal for a person to review. Nothing was posted, changed or paid.

## Summary

Proposed 8 findings. High: u03's 60 round-thousand quarter-end entries to 6960 ($783,796.79 on the account; amounts up to $24,000, below the CFO limit). Medium: u06's Q3 digit anomaly (17.4x chance); u05's after-hours and weekend postings from July; u07 (15) and u08 (10) post-close entries with no approver; u01's 20 entries to Owner equity ($334,696.39); four unverified vendor bank changes. Low: u01's $31,862.40 post-close entry citing memo AA-2025-014, approved by CFO; the memo and its date need to be obtained. Cleared: u24's 12 monthly rent entries ($18,000, same description, system source, 09:15 each month); u24's unusual accounts (3,128 of its entries are system-sourced); no holiday postings; Q1, Q2 and Q4 digit tests close to Benford; weekend entries by u01 (8) were not drilled. Role-peer scan listed u24, u11, u03, u04, u13, u10, u09 and u08; I profiled all eight, plus u06, u05 and u01. Only u03's 6960 and 6950, and u01's equity, were unexplained; the rest are routine site-specific accounts. u11's 15 Fixed assets entries came from the AP subledger and were approved by controller or CFO, so I left them out.

## Findings (8)

### 1. u03: 60 round-thousand entries to Special project consulting (6960) at quarter-end

**Risk:** high
**Population:** All 62 journal entries posted by u03 to account 6960 (total $783,796.79); round_dollar_scan flagged 60 of them as exact multiples of $1,000.
**Procedure:** round_dollar_scan by user and account; role_peer_account_scan Q1/Q3/Q4; user_account_profile u03; list_journal_entries for u03 on 6960 (Mar, Jun, Sep, Dec); compared approvers and amounts with the approval limits.
**Criteria:** Expense postings should rest on supported, non-round amounts; entries near an approval limit should not be split; accounts should fit the poster's role and the description. Approval limits: controller from $5,000, CFO from $25,000.
**Condition:** u03 (senior accountant, Phoenix) posted 60 round-thousand entries to 6960 (60 of the account's 65 lines are round), debiting 6960 and crediting 2100 Accrued liabilities. They cluster on the last days of quarters (8 entries on 2025-03-28 from $2,000 to $22,000; 9 on 2025-06-30; 9 or more on 2025-09-29). Amounts reach $24,000, just under the $25,000 CFO limit. u01 (controller) approved 49 entries ($753,000); u04 (senior accountant) approved 13 small ones. Descriptions are generic and rotate ("Prepaid amortization", "Reclass between accounts", "Month-end correction") and do not fit a consulting expense. Among senior accountants, only u03 uses 6960.
**Cause:** Not determinable from the data. Possibly consistent with quarter-end smoothing or splitting larger amounts below the CFO limit.
**Effect:** $783,796.79 of expense on one account with no visible support; daily totals (for example 2025-03-28) exceed $25,000 although each entry is under it, so CFO review may have been avoided.
**Recommendation:** Obtain contracts, invoices and approvals for each 6960 entry; compare daily quarter-end totals with the CFO limit; ask u03 and u01 about the business purpose and the credit to 2100; extend testing to account 6950 (2 entries by u03).
**Evidence:** journal_entries JE-2025-003323, JE-2025-003345, JE-2025-003401, JE-2025-003422, JE-2025-003448, JE-2025-003463, JE-2025-003469, JE-2025-003474, JE-2025-003481, JE-2025-003562, JE-2025-003565, JE-2025-003626, JE-2025-003633, JE-2025-007138, JE-2025-007204, JE-2025-007216, JE-2025-007239, JE-2025-007268, JE-2025-011035, JE-2025-011068
  - journal_entries JE-2025-003323: $17,000 'Month-end correction' approved by u01
  - journal_entries JE-2025-011035: $24,000, just under CFO limit

### 2. u05: repeated after-hours and weekend manual postings from July 2025

**Risk:** medium
**Population:** All 907 entries posted by u05 (staff accountant, Phoenix); timing_scan flagged 20 after-hours and 20 weekend entries; listed by period to read times.
**Procedure:** timing_scan after_hours and weekend by user; list_journal_entries for u05 for June to September and later ranges; checked posting times in Phoenix local time (MST), approvers and amounts.
**Criteria:** Business hours are 07:00 to 19:00 local, Monday to Friday. Postings outside these hours should be exceptional and supported.
**Condition:** u05 had no after-hours or weekend entries in June (0 of 71) but from 2025-07-01 posted manual entries between 00:08 and 04:44 MST or at 21:35 to 23:52 MST, and on weekends (2025-07-12, 07-13, 07-20, 08-02, 08-03). Examples: JE-2025-007316 at 00:08; JE-2025-009079 at 23:52 ($4,909.74). Several exceed $5,000: JE-2025-007610 $9,089.89; JE-2025-007919 $9,679.20; JE-2025-008707 $38,287.72 on a Saturday, approved by u02 (CFO). Small items were mostly approved by senior accountants u03/u04. The scan counts 20 per rule; 20 flagged entries are cited.
**Cause:** Not determinable from the data. Possibly a change in work pattern, or use of the credential outside normal hours from July.
**Effect:** Out-of-hours entries get less oversight; the flagged set includes amounts over $5,000, one of $38,287.72.
**Recommendation:** Ask u05 and the approvers about the change from July; check access logs for those timestamps; obtain support for the larger flagged entries; review the flagged entries not cited here.
**Evidence:** journal_entries JE-2025-007277, JE-2025-007316, JE-2025-007408, JE-2025-007610, JE-2025-007661, JE-2025-007871, JE-2025-008949, JE-2025-009079, JE-2025-009210, JE-2025-009256, JE-2025-009999, JE-2025-010248, JE-2025-007658, JE-2025-007659, JE-2025-007660, JE-2025-007919, JE-2025-007920, JE-2025-008707, JE-2025-008708, JE-2025-008709
  - journal_entries JE-2025-008707: Saturday, $38,287.72, approved by u02

### 3. u07: 15 post-close manual entries with no approver (Jul 2025 to Jan 2026)

**Risk:** medium
**Population:** All manual entries with no approver (25, via list_journal_entries has_approver=false) and post_close timing_scan results; 15 belong to u07 (staff accountant, Phoenix), total $10,272.41.
**Procedure:** timing_scan post_close by user; list_journal_entries source manual has_approver false over the year; compared posting dates with period close dates from describe_data.
**Criteria:** Entries posted after the period close date need an approver and a stated reason. Approval limits: controller from $5,000, CFO from $25,000; manual entries are expected to carry an approver.
**Condition:** u07 posted 15 manual entries after the period close date, none with an approver and most with no description. Examples: JE-2025-007944 (entry date 2025-06-06, posted 2025-07-21 after the 2025-07-08 close, $4,248.02 to 6500 Depreciation); JE-2025-010486 ($3,557.95, posted 2025-09-17 for August); JE-2025-013067 ($1,528.51). Each debits an expense and credits 2100 Accrued liabilities. The pattern repeats monthly from July 2025 to January 2026. Individual amounts are under $5,000.
**Cause:** Not determinable from the data. Possibly late corrections posted without going through approval.
**Effect:** $10,272.41 of expense and accrual changes recorded after close with no review; period results already closed may have been altered.
**Recommendation:** Ask u07 and the controller why these were posted after close with no approver; obtain support; check whether the system allows posting to closed periods without approval and review other periods for the same pattern.
**Evidence:** journal_entries JE-2025-007910, JE-2025-007944, JE-2025-008023, JE-2025-008044, JE-2025-009007, JE-2025-009151, JE-2025-010486, JE-2025-010572, JE-2025-010755, JE-2025-011686, JE-2025-011745, JE-2025-013067, JE-2025-014227, JE-2025-014974, JE-2025-014975
  - journal_entries JE-2025-007944: $4,248.02 posted 2025-07-21 for June

### 4. u08: 10 post-close manual entries with no approver and terse descriptions

**Risk:** medium
**Population:** All manual entries with no approver (25) and post_close timing_scan results; 10 belong to u08 (staff accountant, Dallas), total $5,425.93.
**Procedure:** timing_scan post_close by user; list_journal_entries source manual has_approver false; compared posting dates with close dates from describe_data.
**Criteria:** Entries posted after the period close date need an approver and a stated reason. Approval limits: controller from $5,000, CFO from $25,000; manual entries are expected to carry an approver.
**Condition:** u08 posted 10 manual entries after period close with no approver, from 2025-07-18 to 2025-12-12. Descriptions are terse user-supplied text such as "per JM", "adj", "corr", "fix", "reclass". Examples: JE-2025-009368 ($2,609.53 to 6210, posted 2025-08-22 for a July-dated entry); JE-2025-009328 ($1,526.99); JE-2025-007905 ("per JM", $130.93). Each credits 2100 Accrued liabilities. Amounts are below $5,000.
**Cause:** Not determinable from the data. Possibly late corrections posted without approval; "JM" is not identifiable from the data.
**Effect:** $5,425.93 recorded after close with no review or documented support.
**Recommendation:** Ask u08 who "JM" is and obtain support for each entry; review why no approver was recorded; check the system's period-lock and approval settings at the Dallas site.
**Evidence:** journal_entries JE-2025-007905, JE-2025-009100, JE-2025-009169, JE-2025-009328, JE-2025-009368, JE-2025-011683, JE-2025-011772, JE-2025-013051, JE-2025-014005, JE-2025-014146
  - journal_entries JE-2025-007905: user-supplied text 'per JM'

### 5. u01: $31,862.40 post-close inventory adjustment citing memo AA-2025-014

**Risk:** low
**Population:** Post_close timing_scan flagged one u01 entry (JE-2025-011864); read with get_records.
**Procedure:** timing_scan post_close; get_records on JE-2025-011864; compared posting time with the September close date (2025-10-07) and approval limits.
**Criteria:** Post-close entries need documented authorisation dated before posting; amounts of $25,000 or more need CFO approval.
**Condition:** JE-2025-011864 (entry date 2025-09-29) was posted 2025-10-22, 15 days after the 2025-10-07 close, by u01 (controller), debiting 5200 Inventory adjustments and crediting 2100 Accrued liabilities for $31,862.40. u02 (CFO) approved, which fits the $25,000 limit. User-supplied text in the description claims "Post-close adjustment per CFO memo AA-2025-014: inventory count variance, approved by M. Chen 2025-10-20". The memo is not visible in the data, so the claim is not verified; the credit is to accruals rather than inventory.
**Cause:** Not determinable from the data. Consistent with a claimed inventory count correction authorised after close.
**Effect:** $31,862.40 of cost of sales moved into a closed period; valid only if the memo exists and predates posting.
**Recommendation:** Obtain memo AA-2025-014, confirm its date (claimed 2025-10-20) and signatory against the 2025-10-22 posting; confirm why the credit went to 2100 and not Inventory.
**Evidence:** journal_entries JE-2025-011864
  - journal_entries JE-2025-011864: Posted 2025-10-22 after 2025-10-07 close; approved by u02

### 6. u01: 20 manual entries crediting Owner equity (3000) against expense/prepaid accounts

**Risk:** medium
**Population:** All 20 entries touching account 3000 (list_journal_entries; total $334,696.39), all posted by u01; account profile of u01 (role has one holder, so role_peer_account_scan skips it).
**Procedure:** list_journal_entries on account 3000; user_account_profile u01; get_records JE-2025-014637; compared approvers with the limits.
**Criteria:** Equity accounts should seldom be touched by routine manual entries; each needs documented support and independent approval, with CFO approval from $25,000. Descriptions should match the accounts used.
**Condition:** u01 (controller) posted 20 manual entries in 2025 involving 3000 Owner equity, total $334,696.39, with generic descriptions ("Reclass between accounts", "Accrual true-up", "Prepaid amortization"). Example: JE-2025-014637 debits 6400 Professional fees $5,235.97 and credits 3000. Large entries: JE-2025-011226 $159,361.15 (2025-09-30), JE-2025-008247 $60,164.81, JE-2025-000130 $30,119.27, JE-2025-006937 $28,587.35, all approved by u02 (CFO). Ten entries were approved by u02; six by u03 and four by u04, both senior accountants who report below the controller.
**Cause:** Not determinable from the data.
**Effect:** Equity and expense balances may be misstated by up to $334,696.39 if entries are unsupported; subordinates approving the controller's entries weakens independence.
**Recommendation:** Obtain support for each 3000 entry, especially the four of $28,000 or more; ask u01 and u02 about their purpose; review whether senior accountants should approve controller entries.
**Evidence:** journal_entries JE-2025-011226, JE-2025-008247, JE-2025-000130, JE-2025-006937, JE-2025-003149, JE-2025-005145, JE-2025-009601, JE-2025-014637, JE-2025-001472, JE-2025-002545, JE-2025-007728, JE-2025-008206, JE-2025-008638, JE-2025-009149, JE-2025-010409, JE-2025-010585, JE-2025-010595, JE-2025-011202
  - journal_entries JE-2025-011226: $159,361.15 on 2025-09-30, approved by u02
  - journal_entries JE-2025-014637: Expense debit, equity credit

### 7. u06: Q3 manual entries with first-digit distribution far from Benford (17x chance)

**Risk:** medium
**Population:** u06 (staff accountant, Phoenix): 4,894 GL lines for the year; 2,880 lines in 2025-Q3 (575 entries, all manual); compared with u06 in Q2 (666 lines).
**Procedure:** benford_first_digit by quarter (Q3 nonconforming, MAD 0.022) and group_by poster (u06 mad_over_chance 17.43); benford_first_two_digits for Q3 and for u06 Q3; gl_population_profile; user_account_profile u06; list_journal_entries for u06 in Jul, Aug, Sep; get_records on three entries.
**Criteria:** Amounts in a natural population should follow Benford's law; a poster-level mad_over_chance of 5 or more is far beyond chance. Manual entries should be explained by support and approved within limits.
**Condition:** The whole GL is close to Benford in Q1, Q2 and Q4 (MAD 0.0028 to 0.0038) but not in Q3 (MAD 0.022, n=13,068). Among posters, u06 has MAD 0.0585 against 0.0034 expected by chance (17.43x); the next poster is 2.13x. For u06 Q3 alone (2,880 lines, descriptive only) digits 5 to 8 make up about 75% of lines against 29% expected, driven by leading pairs 79, 89, 77, 81, 84 (z 11 to 14). Q3 contains a surge of 6-line manual entries (for example JE-2025-007283, JE-2025-008665, JE-2025-008712), each debiting several expense accounts and crediting 2100 Accrued liabilities, with generic descriptions. Approvers are u01 (294 entries $3.02M for entries ≥$5,000), u02 (20 entries $1.67M) and, in late September, u03/u04. u06's account mix matches peers, so account choice is not the signal; the digit pattern is the signal.
**Cause:** Not determinable from the data. Possibly consistent with amounts chosen or generated rather than arising from transactions, or a bulk or template process in Q3.
**Effect:** Q3 manual accrual and expense postings of $4,693,469.29 across 314 entries of $5,000 or more may include amounts without genuine support; the effect on results is not determinable.
**Recommendation:** Obtain support for a sample of u06's Q3 entries, particularly 6-line entries over $5,000; ask u06 and u01 how they were prepared and why volume rose in Q3; compare with Q2 and Q4 workload.
**Evidence:** journal_entries JE-2025-007283, JE-2025-007285, JE-2025-007302, JE-2025-007324, JE-2025-007326, JE-2025-007352, JE-2025-007354, JE-2025-007359, JE-2025-007377, JE-2025-007389, JE-2025-007418, JE-2025-007420, JE-2025-008665, JE-2025-008712, JE-2025-008759, JE-2025-010677, JE-2025-010707, JE-2025-010748, JE-2025-007371, JE-2025-010696
  - journal_entries JE-2025-007283: 6-line entry, $13,744.04, 2025-07-01
  - journal_entries JE-2025-008665: 6-line entry
  - journal_entries JE-2025-008712: 6-line entry
  - journal_entries JE-2025-007371: $88,322.90, approved by u02
  - journal_entries JE-2025-010696: $291,925.80, approved by u02

### 8. Four vendor bank-account changes (Aug to Nov 2025) have no verifier or callback note

**Risk:** medium
**Population:** All 8 vendor_bank_changes records (get_records); 4 lack a verifier and verification note.
**Procedure:** get_records on vendor_bank_changes 1 to 8; compared changer, verifier and verification note for each change.
**Criteria:** Each change to a vendor's bank account should be verified independently (callback to the number on file) by someone other than the person who made the change, and the verification recorded.
**Condition:** Changes 4 (V0101, 2025-08-18, by u11), 6 (V0024, 2025-09-29, by u10), 7 (V0093, 2025-10-27, by u11) and 8 (V0092, 2025-11-14, by u10) have verified_by empty and no verification note. The other four (1, 2, 3, 5) carry a verifier (u03 or u04) and a callback note. Changers u10 and u11 are AP clerks. Changes 4, 6, 7 and 8 occurred after July and none is verified.
**Cause:** Not determinable from the data. Possibly verification lapsed after mid-2025, or verifications were not recorded.
**Effect:** Payments to these four vendors after the change could go to an unverified account; amounts paid were not tested here, so the exposure is not determinable.
**Recommendation:** Obtain callback evidence for the four changes; review payments to V0101, V0024, V0093 and V0092 dated after each change; confirm who can change bank details and whether verification is enforced.
**Evidence:** vendor_bank_changes 4, 6, 7, 8
  - vendor_bank_changes 4: V0101, changed by u11, no verifier
  - vendor_bank_changes 6: V0024, changed by u10, no verifier
  - vendor_bank_changes 7: V0093, changed by u11, no verifier
  - vendor_bank_changes 8: V0092, changed by u10, no verifier

## Checked

- Benford first-digit by quarter, first-two-digit for Q3, poster ranking
- round_dollar_scan by user and by account
- timing_scan: weekend, holiday, after_hours, post_close, last_3_days_of_period
- role_peer_account_scan Q1, Q3, Q4; user_account_profile for u24, u11, u03, u04, u13, u10, u09, u08, u06, u05, u01
- Manual entries with no approver (25, all post-close, u07/u08)
- Approver roles against $5,000 and $25,000 limits on flagged entries
- Account 3000 postings; u24 rent entries; u11 Fixed assets entries
- vendor_bank_changes (all 8)

## Not checked in this run

- Role-peer scan for Q2 was not run (Q1, Q3 and Q4 were)
- Last-3-days-of-period flags were not drilled (every poster is about 25%, a general pattern)
- u01's 8 weekend entries were not read
- Invoices, payments, purchase orders and vendors were not tested, including payments after the bank changes
- Remaining u05 flagged entries beyond the 20 cited were not read
- The first-digit test was not run on subsets of users other than u06
- Use-tax rules (get_regulation) were not applied
- u24's payroll-source entries were not read
