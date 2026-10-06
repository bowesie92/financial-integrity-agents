# Financial Integrity Agents: Scope

## Purpose
Two propose-only reasoning agents investigate synthetic accounting data the way an audit senior would and write up findings for human review. They never act on a finding.

## Company and data
- Sonoran Ridge Supply Co., a fictional industrial and building supplies distributor. Headquarters in Phoenix, AZ, with branches in Dallas, TX and Fresno, CA.
- Period: calendar 2025, reviewed as of 2026-01-31.
- Volume: about 45,000 GL lines in 15,000 journal entries, 120 vendors, 1,200 purchase orders, 1,800 invoices.
- All data is synthetic and generated from a fixed random seed. No real company, person, or account is used.
- Business hours are 07:00 to 19:00 local time, Monday to Friday. Arizona does not observe daylight saving time, so timestamps are stored in UTC with each site's time zone and judged in local time.
- Approval limits: Controller from $5,000, CFO from $25,000.
- AP records mirror the fields of a QuickBooks Online bill (vendor, dates, document number, account lines, total, memo), so AP Guardian reads the same shape as the author's AP automation MVP.

## The two agents
- AP Guardian is a cross-invoice reasoning layer. Per-invoice checks look at one invoice at a time; Guardian looks across invoices for duplicates, split invoices, vendor anomalies, and bank-detail changes.
- GL Sentinel automates journal entry testing: Benford digit tests, round-dollar frequency, timing checks, post-close entries, and unusual user-account pairings. It decides which flags deserve a closer look and writes a workpaper-style finding.
- Both write proposals to a findings table with status "proposed". Their database role can read data and insert findings only.

## Planted patterns (ground truth)
| Agent | Pattern | Count |
| --- | --- | --- |
| GL Sentinel | Benford violation: fabricated manual accrual entries in Q3 expense lines, calibrated so first-digit MAD is above 0.015 while clean quarters stay under 0.006 | 1 quarter |
| GL Sentinel | Round-dollar cluster at period end, one user, seldom-used account | about 60 entries |
| GL Sentinel | Weekend and after-hours postings in local time, one user | about 40 entries |
| GL Sentinel | Post-close entries with little or no description | about 25 entries |
| GL Sentinel | Unusual user-account pairing: a user who never posts to that account | about 15 entries |
| AP Guardian | Split invoices just under the $5,000 approval limit | 4 groups |
| AP Guardian | Exact duplicate invoices | 6 |
| AP Guardian | Near-duplicate invoices | 6 |
| AP Guardian | Large first invoice from a new vendor | 3 |
| AP Guardian | Purchase order mismatches | 8 |
| AP Guardian | Amount outliers for a known vendor | 6 |
| AP Guardian | Vendor bank-detail change shortly before a large payment | 4 |
| Red team | Invoices whose memo or vendor-name text contains instructions to the agent | 8 |

## Decoys (look suspicious, are legitimate; the agent must clear them)
- Identical monthly rent and payroll entries.
- Month-end weekend postings by the controller.
- A vendor that legitimately sends identical invoices.
- A large first invoice that has a purchase order and an approval.
- Fresno after-hours postings that fall inside that branch's normal hours.
- A post-close adjustment with documented CFO approval.

## Out of scope
- A multi-company, multi-tenant platform (documented as how this scales).
- MCP and Anthropic Academy courses.
- A user interface, fine-tuning, or real company data.
- Any action taken on a finding: approving, paying, posting, or editing records.

## Priorities if time slips (cut from the bottom up)
1. Must: the original GL and AP patterns, the decoys, the success metrics, the memo format, the failure catalog, and the README case study.
2. Should: post-close entries, bank-detail changes, the red-team slice, and the rules-only baseline.
3. Stretch: a Haiku versus Sonnet and Bedrock comparison table.

## Definition of done
- The data generator is reproducible from its seed and ground truth is stored where the agent cannot read it.
- Both agents run end to end and produce memos with record-level evidence.
- The evaluation harness reports every metric against its target.
- The README opens with a real sample memo, then a real tool-call transcript, a cost table, and a failure catalog.
- A demo recording and a short case study exist, and a secrets scan of the full history is clean before the repo goes public.

## What this project does not claim
The agents flag items for human review with evidence. They do not conclude that fraud occurred.
