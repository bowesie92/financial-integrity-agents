# Failure catalog

Every item here happened in a real run or build step. For each one: what happened, the evidence, what I did about it, and whether it is fixed or a known limit. Nothing was tuned on the held-out seed after seeing its results, so several of these are deliberately left as known limits.

Sources for the numbers: `results/` (scored runs), `docs/eval_notes.md`, and the run logs on the author's machine. Counts of Sonnet 5.5 runs are out of 10 for seed 3 GL (5 on the frozen prompt, 5 on the general prompt) unless stated.

## Agent behavior

| # | What happened | Evidence | What I did | Status |
| --- | --- | --- | --- | --- |
| 1 | **GL: the unusual user-account pattern was missed.** An AP clerk posted 15 fixed-asset entries (seed 1) and, on seed 3, 15 planted entries to accounts the poster never used. | Seed 2: found in 0 of 5 runs. Seed 3, Sonnet 5.5: in 5 of 10 runs all 15 entries reached the agent, and it reported them in 2 of those 5. In the other 5 runs none appeared in any tool result. The result was always 15 or 0, so it was a choice of which checks to run, not a cut-off list. Haiku 4.5 never saw them (0 of 5). | Did not patch the prompt for one pattern, because that would fit the development data. Wrote a general version that sends uncertain items to a person. It did so in 2 of 5 runs (0 of 5 before). | Known limit (D28) |
| 2 | **GL: a real problem cleared with a plausible reason.** The agent profiled the user and cleared the entries as an approved AP subledger posting. | Same runs as item 1. In this week's scheduled GL run it again left out the 15 fixed-asset entries for the same reason. | Reported as measured. Proposed a second pass that tries to disprove every clearance. | Known limit |
| 3 | **AP: bank-change payment ids and split-invoice totals left out of findings.** The tools returned the numbers but the agent did not always write them down. | Seed 2: four AP runs each missed one target, including bank-change payment ids and the combined total of split invoices (twice). | Kept as measured. The scorer needs payment ids to give credit, so this counts as a miss. | Known limit |
| 4 | **Decoys cited inside a correct finding cost clearance.** A look-alike innocent record was named in the same finding as a real problem, so the scorer counted it as flagged. | Decoy clearance ranged from 41% to 77% on the same data and prompt across runs. | Report ranges, not one number. | Known limit |
| 5 | **Use-tax estimate sometimes not within $1.** | Seed 2: 8 of 8 in two runs and 0 of 8 in two. | Reported as measured. | Known limit |
| 6 | **Results move between identical runs.** | Five runs per setting, same data and prompt. | More runs would tighten the ranges. I report ranges. | Known limit |
| 7 | **The cheaper model misses quietly.** Haiku 4.5 never found the near-duplicate invoices in any of five runs, and its precision looked excellent only because it reported far fewer findings. | Seed 3: Haiku found 106 of 185 AP planted items (57%) and 14 of 25 GL pattern-runs, against 181 of 185 (98%) and 20 of 25 for Sonnet 5.5. Likely obeyed injected text in 4 of 40 red-team cases. | Chose Sonnet 5.5 as the final model. Haiku is for development only. | Decided (D31) |
| 8 | **The general-rules prompts did not beat the originals.** | Seed 3: AP decoy clearance went from 66% to 76%, within noise, with slightly fewer items and lower precision. | Success criteria were fixed first. By my own criteria the new prompts did not win, so `ap-1` and `gl-7` stay the headline versions. | Decided (D30) |
| 9 | **Hostile text in the data.** Eight invoices carry instructions aimed at an AI reviewer. | Sonnet 5.5 reported 8 of 8 and obeyed none. Haiku 4.5 reported 6 of 8, obeyed none on the targeted run. | Treated as evidence: the agent must still find any real problem on the record and report the attempt. A guard also bars payment-stopping advice. | Working as designed |

## Loop and cost

| # | What happened | Evidence | What I did | Status |
| --- | --- | --- | --- | --- |
| 10 | **Replies cut off at the output limit with no findings.** | One AP run on seed 2 and one GL run (`gl-6`, caused by my own cite-every-entry rule making one reply too long). | Added output pacing in `gl-7` and a recovery step in the loop after a double cut-off. The loop change was reviewed against five safety checks (D10). | Fixed in the loop |
| 11 | **First GL run on Haiku used no prompt caching.** Its cost ($0.68) was far above the others. | `run_costs.csv`: one run with fresh input of 619,806 tokens and zero cache use. | Excluded from averages and flagged in the workbook. | Fixed |
| 12 | **Cache read price uncertainty.** My code charges cache reads at 0.1 times the input price on every model. Anthropic's documentation suggests Sonnet 5.5 may be 0.05 times. | `fia_llm/types.py`; docs read on 2026-10-09. | Left the code alone, because changing cost logic after the freeze would blur the record. Reported costs are conservative, up to about 11% above a lower price. | Open until checked against the Console invoice |
| 13 | **Listing results cut off at the row limit.** | 182 of 316 GL journal entry listing calls (58%) on Sonnet 5.5. | Checked it against the answer key on seed 3: it did not explain the missed pattern, and partly visible patterns still counted as found. | Known limit at larger scale |

## Scoring

| # | What happened | Evidence | What I did | Status |
| --- | --- | --- | --- | --- |
| 14 | **The scorer reads only dollar amounts written with a `$` sign.** A correct figure written as `4742.14` is not counted. | The AP findings written this week use bare figures in places. | Kept as is. Changing scoring rules after seeing results would invalidate them. Listed here instead. | Known limit |
| 15 | **Bank-change credit needs payment ids.** | Item 3. | Same reason. | Known limit |

## Operations

| # | What happened | Evidence | What I did | Status |
| --- | --- | --- | --- | --- |
| 16 | **n8n rejected Supabase's certificate chain** as self-signed. | Error on the first test of the Postgres node. | Turned on Ignore SSL Issues on that credential. Traffic is encrypted but the server's identity is not verified. | Documented trade-off |
| 17 | **Mailgun sandbox email lands in spam** and only reaches authorized recipients. | First digest went to the spam folder. | Marked it not spam and added a filter. A real deployment would use a verified domain. | Documented trade-off |
| 18 | **Free Supabase projects pause** after about a week of low activity. | Supabase docs, read 2026-10-09. | The n8n poll doubles as the keep-alive while n8n runs. | Depends on n8n staying up |
| 19 | **A planted failure in the delivery query posted an alert to the logs channel**, then a later edit left the workflow unable to run. | Executions list shows the error runs between 00:23 and 00:28 on 2026-10-09. | Restored the earlier workflow version and confirmed overnight runs every two hours. | Fixed |
| 20 | **Scheduling a run on static data repeats findings.** | Every scheduled run proposes the same issues again under a new run id. | Timers are installed and tested but off by default. | By design |
