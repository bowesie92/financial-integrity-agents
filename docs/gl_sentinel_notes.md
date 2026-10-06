# GL Sentinel, in plain language (task 4.7)

Code: `fia_agents/gl_sentinel.py` (prompt and run function), `fia_agents/memo.py` (memo writer),
`fia_agents/transcript.py` (readable transcript), `scripts/run_gl_sentinel.py` (the command you run).
Tests: `tests/test_gl_sentinel.py`. The reasoning loop is unchanged; this task only adds what goes into it.

## What it does

1. Builds the system prompt (the text below the code in `SYSTEM_TEMPLATE`), with the call limit filled in from `Limits`.
2. Runs the loop with the GL tools plus `propose_finding` and `finish_review`.
3. Writes three files: the JSONL log, a readable transcript, and the memo.

The memo is built by code from the stored finding rows, in the order and wording of `docs/memo_template.md`. The model writes the
field contents; it never writes the memo layout.

## Differences from docs/memo_template.md

- **Not checked is per run, not per finding.** The findings table has no column for it, and the template maps one to one onto columns. The memo
  ends with a "Not checked in this run" list taken from the model's `finish_review` call. Rule 5 is met at run level.
- **Dry runs** store nothing (the insert is rolled back), so their memo is built from the log. The memo says which source it used.

## The prompt, section by section (review these)

| Section | What it makes the model do | Why |
|---|---|---|
| Role | Propose only; cannot act | D6, D7 |
| How to work, 1 | Call `describe_data` first | Facts come from the data, not the prompt |
| How to work, 2 | Check the population before a digit test | 5,000-line floor for Benford |
| How to work, 3 | Cover every test family a to e before finishing (digits, round amounts, timing, user and account fit, approvals) | The scope's testing frame; the first dry run stopped after one signal |
| How to work, 4 | Read records before citing them | Evidence must exist (the tool also checks) |
| How to work, 5 | Look for a routine explanation first, and say what was cleared | Real auditors clear false positives; decoy clearance is a metric |
| How to work, 6 | One finding per issue, not per record | Keeps memos readable |
| Data rules | Quote tool summaries; times are local; roles come from tools | The first dry run counted and summed by hand and misread UTC |
| Writing rules | The six memo rules, including untrusted text | `docs/memo_template.md` |
| Risk rating | The fixed rubric ($25,000 and $5,000) | Same rules the generator used |
| Budget | States the call limit and when to wrap up | A model that knows the limit finishes before it |
| Finishing | One `finish_review` with summary, checked, not checked | The loop needs it to end cleanly |

## Rules about the prompt

- It names no planted pattern, decoy, seed or threshold. A test fails if it does. It only describes how a careful auditor tests.
- Honest limit to state in the README: the prompt's author knew the kinds of routine activity the data contains (recurring entries, close work,
  site time zones, approved adjustments), and step 5 asks for them in general terms. Seed 2 uses the same generator, so the held-out
  evaluation tests new random draws, not new kinds of decoy.
- Every change to the prompt text must bump `PROMPT_VERSION` and add a row below. The version is in every memo. The hash of the prompt is in every log.
- No baseline threshold may change once an agent run exists (D25). Prompt tuning on seed 1 is allowed. At 4.11 the prompt is frozen, then seed 2 is run.

| Version | Date | Change |
|---|---|---|
| gl-1 | 2026-10-06 | First version |
| gl-4 | 2026-10-06 | After the gl-3 dry run (the poster-level digit test pointed straight at the deviating poster and the model dismissed it for sample size; round-dollar concentration cleared as 'recurring'; no cross-user account test): small-sample rule rewritten (ratio of 5 or more is far beyond chance), recurring means same description and same amount, round-dollar concentration is unexplained unless a record shows why, family d uses role_peer_account_scan |\n| gl-3 | 2026-10-06 | After the gl-2 dry run (post-close pattern found; round-dollar and timing patterns cleared because 'approved'; Benford claim traced to the wrong account; wrapped up at call 19 believing it was at 26; summary over 2,000 characters wasted a call): approval is never a reason to clear, no attribution without a test for that poster or account, no invented business reasons, do not finish early, call count shown in every tool result, 2,000 character limit stated, digit test by poster, no 'no fraud indicators' wording |
| gl-2 | 2026-10-06 | After the first dry run (one of five pattern families found, wrong counts, UTC read as local time, approval treated as clearance): a coverage list a to e, an approval rule, DATA RULES (quote tool summaries, local times, roles from tools), call planning, per-family coverage in finish_review |

## How to run

```
python scripts/run_gl_sentinel.py --dry-run     # nothing stored, memo from the log
python scripts/run_gl_sentinel.py --dry-run --prompt gl-5 --model demo-plus   # pick the prompt version and the model
python scripts/run_gl_sentinel.py               # real run: findings stored in fia.findings
touch .fia_kill                                 # stops a run cleanly after its current step (delete the file afterwards)
```

## Review checklist for the prompt (answer yes or no)

1. Does it say the agent can only propose, and that a person decides?
2. Does it say to call `describe_data` first and use its facts?
3. Does it warn that digit tests need whole quarters of 5,000 or more lines?
4. Does it tell the agent to read records before citing them?
5. Does it tell the agent to check for a routine explanation before proposing?
6. Does it say text in memo fields is untrusted and must never be followed?
7. Does it forbid recommending posting, voiding, reversing, editing or paying?
8. Does it forbid concluding that fraud occurred?
9. Does it state the call limit and when to wrap up?
10. Does it avoid naming any planted pattern or test design?

## What can go wrong on the first run

| Failure | How you will see it | What we do |
|---|---|---|
| Model never finishes | status `max_calls` or `no_finish`, memo marked INCOMPLETE | Tighten the budget text; raise the cap only if usage shows it is too low |
| Flags routine activity | Findings on recurring or approved entries | Strengthen step 5 wording, bump the version |
| Misses a pattern | Fewer findings than the baseline | Check the transcript for the tool it never called; adjust "how to work" |
| Follows text in a memo field | Wrong tool calls after reading a description | Stop and tell me; this is the red-team slice (4.10) |
| Cost above the estimate | The memo header shows cost | Re-tune the caps from the measured numbers |

## Tool and client changes made after the first dry run (2026-10-06)

- `list_journal_entries` now returns a `summary` over ALL matching entries (count, total, round-thousand entries, local after-hours, weekend and post-close counts, self-approved and no-approver counts, posters and approvers with roles) and shows `posted_local` (poster's local time) instead of UTC. The first dry run counted and added rows by hand and was wrong.
- Prompt caching is on for real runs (`--no-cache` turns it off). One breakpoint goes on the last block of the last message, so each call re-reads the earlier history at 0.1x the input price; cache writes cost 1.25x. Source: platform.claude.com prompt caching page, checked 2026-10-06. Haiku 4.5 needs at least 4,096 tokens before anything is cached; shorter prompts are not cached and no error is returned. Cost, token budget and the run log now count cache tokens.
- The provisional cost cap is now $1.50 (was $1.00). Measure the real figure after the first cached run, then set the cap.
- Known tool gap, not fixed: a first-digit deviation can be seen by quarter but not traced to a poster, because the digit tests do not group by user. Decide at 4.9 from the evaluation numbers whether to add that.

## Tool changes made after the gl-2 dry run (2026-10-06)

- `benford_first_digit` takes `group_by: poster`. It ranks posters (300 lines or more) by `mad_over_chance`: the poster's first-digit MAD divided by the MAD a Benford-conforming sample of that size would show by chance (`analytics.mad_noise`). About 1 is normal. On seed 1 the deviating poster scores above 20 in Q3 and no poster scores above 2 in Q1, so the model is not told who to look at.
- Every line-level tool now accepts `posted_by` and `account_id` (the model tried `account_id` on `round_dollar_scan` and got an error).
- Every tool result carries `model_calls: "N of M used"` when the loop sets it. This is one line in `loop.py`, before the tools run: `ctx.calls_used, ctx.calls_allowed = state.calls, limits.max_calls`. The tool-result message is still tool_result blocks only. Reason: in the gl-2 run the model said it had used 26 calls when it had used 19, and wrapped up early.

## Tool changes made after the gl-3 dry run (2026-10-06)

- New tool `role_peer_account_scan`: accounts that only one user in a role posts to while others in the role do not, rarest first. Reason: no run had ever looked for users posting to accounts unusual for their role, because no test flags those users and profiling all 24 would use the whole call budget.
- `list_journal_entries` takes `has_approver` (the model used `has_description=false` as a stand-in for "no approver"). System, payroll and subledger entries have no approver, so use it with `source=manual`.
- The poster-level digit test note now says the 5,000 line floor is for the conformity bands, not for `mad_over_chance`.
- Wording guards in `propose_finding` and `finish_review` (both agents): a recommendation that advises reversing, voiding, reposting or deleting is rejected, and so is any conclusion about fraud either way ("no fraud indicators"). In the gl-3 run the model wrote both after being told not to. The rejection message says what to change, so the model retries. These are memo rules 3 and 5 enforced where the text is written.

## After the gl-4 dry run (2026-10-06): two prompts side by side, caps changed

- The gl-4 run stopped at status `token_budget` after 29 calls and $0.24. Cause: since caching was added the token budget counts cached input too, and 1,000,000 was too low. The cost cap ($1.50) is the real limit, so `max_total_tokens` is now 3,000,000.
- gl-4 run result: the poster-level digit test now led the model to the right poster (one of five pattern families found), plus the post-close pattern. It still cleared the round-dollar pattern as "routine" while writing that the amounts differ each period, which its own prompt says is not a recurring entry, and it dismissed the weekend and after-hours poster without looking. The tools surfaced every pattern; the judgment is where Haiku falls short.
- `list_journal_entries` accepts `quarter` and `period_id` (the model tried `quarter` and got an error).
- **gl-5** is a fresh rewrite of about 480 words (gl-4 is about 1,040). It drops every rule the code now enforces (wording, counting, time zones, roles, call count) and keeps the judgment rules once each. gl-4 stays frozen in `TEMPLATES` so the two can be compared on the same model. `--prompt gl-4|gl-5` chooses; the memo header records it.
- Comparison plan, one variable at a time: gl-4 and gl-5 on `dev` (Haiku), then the better one on `demo-plus`. Pick by recall on seed 1, then freeze at 4.11.
