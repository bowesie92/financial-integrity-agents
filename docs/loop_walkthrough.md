# The reasoning loop, in plain language (task 4.6)

Code: `fia_agents/loop.py` (about 150 lines). Limits: `limits.py`. Kill switch: `kill.py`. Log: `runlog.py`.
Tests: `tests/test_loop.py`. Nothing in the loop touches the database directly; only the tools do, and they are read-only.

## What one run does

1. Send the model the system prompt, the task and the tool list.
2. The model replies with text, or with one or more tool requests.
3. For each tool request, run that tool, wrap the result, and send all results back in ONE message.
4. Repeat until the model calls `finish_review`, or something stops the run.

Before every model call the loop asks one question in one place (`check_limits`): has anything told me to stop?

## The rules the loop keeps (review these, they are the core)

1. History is append-only. Nothing earlier is edited or removed. The model's reply is stored exactly as returned.
2. A reply to tool requests is one user message containing only tool results, in the same order, one per request.
3. Every stop has a name and a log line. There is no silent exit.
4. Findings proposed before a stop stay in the database. A stopped run is reported as incomplete, not erased.
5. The model never sets sampling options, never forces a tool, never gets a mid-run text injection except the one nudge.

## Stop statuses

| Status | Meaning | Cause |
|---|---|---|
| finished | Normal end | finish_review was called |
| killed | You stopped it | `.fia_kill` file exists, or Ctrl+C / SIGTERM |
| wall_time | Too slow | 900 s |
| max_calls | Too many model calls | 40 |
| token_budget | Too many tokens | 1,000,000 input plus output |
| cost_budget | Too expensive | $1.00 (skipped if the model has no verified price) |
| no_finish | Model stopped talking without finishing | after one reminder |
| output_truncated | Reply cut off twice, then cut off twice again after one recovery | 4096 tokens, then 8192; the first double cut-off is dropped and the model is asked once to carry on with shorter replies |
| tool_failure | Tools keep failing | 3 internal errors in a row |
| db_error | Database connection closed | |
| llm_fatal | The API call failed for good | bad key, no credit, and so on |
| refusal | The model declined | |
| context_exceeded | Conversation too long | |
| protocol_error | A stop reason the loop does not handle | |

When two limits are hit at once, the first in this order is recorded: killed, wall_time, max_calls, token_budget, cost_budget.

## Provisional numbers

The caps (40 calls, 1M tokens, $1.00, 900 s) are guesses until a real Haiku run measures usage (decision D13 revisit). Change them in `Limits`, nowhere else.

## Review checklist (answer yes or no while reading loop.py)

1. After a `tool_use` reply, is the next message built only from tool_result blocks?
2. Is the model's reply appended unchanged, and is an empty reply never appended?
3. Does `check_limits` run before every model call?
4. Is the kill switch also checked between tools in one turn?
5. Does a tool error become an `is_error` result for the model, not a crash?
6. Do 3 internal errors in a row end the run?
7. Is a closed database connection detected before the next call?
8. Does a cut-off reply retry the same request once, with a bigger limit, and then stop?
9. Is every exit path going through `end()` so `run_end` is always logged?
10. Does the log hold a hash of the system prompt, not the prompt, and no secrets?

## Logs

One JSONL file per run in `runs/` (git-ignored). First line `run_start`, last line `run_end`. Every model call and every tool call, including the model's stated reason, is a line.
