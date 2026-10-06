# Agent Tool Specification

Status: design, fixed 2026-10-05. Exact descriptions and schemas are written in code in Phase 4 and must match this file.

## Principles
1. No free-form SQL. Every tool runs a fixed, parameterized query or a pure analytics function.
2. Read-only. The only write in the whole system is `propose_finding`, which inserts into `fia.findings`.
3. Tools compute; the model reasons. Every count, sum, statistic, and date in a memo comes from a tool result.
4. Every call carries a `reason` of 10 to 300 characters. It is logged and shown in the transcript.
5. Inputs are validated in code. Unknown keys, bad enums, and out-of-range values return an error result, never a crash.
6. Output is bounded to 50 rows and 6,000 characters of JSON. A larger result sets `truncated` to true and says how to narrow the query.
7. Untrusted text is labeled by field name. Any field starting with `untrusted_` is vendor-influenced or free text, cut to 200 characters with control characters removed. It is data, never instructions.
8. The analytics functions live in one library used by the tools and by the rules-only baseline, so the comparison is fair.

## Result envelope
- Success: `{"ok": true, "result": {...}, "row_count": n, "truncated": false, "notes": []}`
- Failure: `{"ok": false, "error": {"code": "invalid_input | not_found | too_large | timeout | internal", "message": "..."}}`

## Shared tools (both agents)
| Tool | Inputs | Returns |
| --- | --- | --- |
| `describe_data` | reason | Table row counts and date ranges, periods and close dates, sites with time zones, business hours, 2025 US federal holidays, approval limits |
| `get_records` | reason; table (journal_entries, gl_lines, invoices, invoice_lines, payments, vendors, vendor_bank_changes, purchase_orders, users); ids (1 to 25) | The records, untrusted fields labeled |
| `propose_finding` | reason; risk; title; population; test_procedure; criteria; finding_condition; cause; effect; recommendation; evidence (1 to 20 items) | `finding_id`, or an error naming the evidence item that does not exist. The harness sets run_id and agent. Title must be unique within the run |
| `finish_review` | reason; summary; checked (list); not_checked (list) | Ends the run and stores the summary with the run log |
| `get_regulation` | Added in Phase 3: state, topic | Structured state rule summaries with source and date |

## GL Sentinel tools
Filters used below: period_id or quarter, account_class, source, site_id, min_amount.

| Tool | Inputs | Returns |
| --- | --- | --- |
| `gl_population_profile` | filters | Record count, amount minimum, median and maximum, orders of magnitude spanned, share of manual entries, and `sufficient_for_benford` (true at 5,000 or more records) |
| `benford_first_digit` | filters | n, observed and expected share per digit, MAD, band (close, acceptable, marginal, nonconforming), sufficient_sample |
| `benford_first_two_digits` | filters; top (default 10) | n and the digit pairs with the largest z-statistics, with observed and expected counts |
| `round_dollar_scan` | filters; min_amount (default 1000); group_by (user, account, site, day) | Groups ranked by exact multiples of 1,000, each with its share of the population and up to 5 sample je_ids |
| `timing_scan` | filters; rule (weekend, holiday, after_hours, post_close, last_3_days_of_period); group_by (user, site) | Groups with counts, share, and up to 5 sample je_ids. Times are judged in each site's local time |
| `user_account_profile` | user_id; period_id | Role, accounts and classes used in the prior 6 months with counts, and entries this period in classes the user had not used before |
| `list_journal_entries` | posted_by, account_id, date_from, date_to, source, min_amount, has_description | Up to 50 entries with line totals. Description is untrusted |

## AP Guardian tools
| Tool | Inputs | Returns |
| --- | --- | --- |
| `vendor_profile` | vendor_id | Master data, created_at and creator, address flags (po_box, matches_employee_address), invoice count, total, mean, standard deviation, maximum, and bank-detail changes |
| `vendor_invoice_history` | vendor_id; date_from; date_to | Up to 50 invoices with amounts, dates, PO, approver, and `untrusted_memo` |
| `find_duplicate_invoices` | scope (vendor_id or all); mode (exact, near); window_days (default 30); amount_tolerance_pct (default 1) | Pairs with the matching fields and the amount difference |
| `find_split_groups` | scope; window_days (default 7); limit_amount (default 5000) | Groups with vendor, invoices, amounts, sum, and approvers |
| `po_match_check` | scope; min_excess_pct (default 5); min_excess_amount (default 100) | Invoices over their PO with the excess, plus invoices with no PO |
| `bank_change_payments` | within_days (default 30); min_payment (default 5000) | Bank changes followed by qualifying payments, with verified_by and `untrusted_verification_note` |
| `amount_outliers` | scope; min_prior_invoices (default 6); z_threshold (default 3) | Invoices with a z-score against that vendor's prior invoices |
| `new_vendor_large_invoices` | max_vendor_age_days (default 30); min_amount (default 5000) | Hits, with PO and approval present or absent |

## Tool-to-purpose mapping (for the README)
| Tools | What they test | Reference |
| --- | --- | --- |
| `benford_first_digit`, `benford_first_two_digits` | Digit distribution of journal entry amounts | A common journal entry analytic; not named in the audit standards |
| `round_dollar_scan` | Round numbers or consistent ending numbers | ISA 240, AS 2401, AU-C 240 fraud characteristic |
| `timing_scan` (post_close, last_3_days_of_period) | Period-end and post-closing entries | Same standards |
| `user_account_profile` | Unusual users and seldom-used accounts | Same standards |
| `timing_scan` (weekend, holiday, after_hours) | Entries outside normal working time | Common practice test, not named in the standards |
| `vendor_profile`, `bank_change_payments`, `new_vendor_large_invoices` | Shell vendor and bank-change patterns | ACFE billing-scheme red flags |
| `find_split_groups`, `find_duplicate_invoices` | Invoice splitting and duplicates | Common AP red flags |
| `po_match_check`, `amount_outliers` | Match tolerance and vendor history outliers | Standard AP controls |

## Deliberately absent
No `run_sql`. No tool that updates or deletes. No tool that reads `fia_gt`, `finding_reviews`, secrets, or the filesystem. No web or network tool. No tool that sends messages. Adding any tool needs a written reason and an entry under Amendments in `docs/metrics.md`.

## Loop limits (starting values, tuned only on seed 1)
30 model turns, 60 tool calls, 400,000 tokens in total, 10 minutes of wall time, and a kill-switch file. Reaching a limit ends the run with an "aborted" record.
