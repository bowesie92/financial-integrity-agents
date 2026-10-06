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
| How to work, 3 | Test the ISA 240 journal entry frame: digits, round amounts, timing, user and account fit | The scope's testing frame |
| How to work, 4 | Read records before citing them | Evidence must exist (the tool also checks) |
| How to work, 5 | Look for a routine explanation first, and say what was cleared | Real auditors clear false positives; decoy clearance is a metric |
| How to work, 6 | One finding per issue, not per record | Keeps memos readable |
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

## How to run

```
python scripts/run_gl_sentinel.py --dry-run     # nothing stored, memo from the log
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
