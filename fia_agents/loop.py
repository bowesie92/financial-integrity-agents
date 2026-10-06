"""The reasoning loop. Read it top to bottom: it is short on purpose.

One run is: ask the model, run the tools it asks for, send the results back, repeat, until it calls
finish_review or a limit stops it. The model never touches the database; every tool is a fixed,
read-only query in fia_tools (D6, D7). Rules the loop keeps:
  1. History is append-only. A reply is appended exactly as returned, thinking blocks included.
  2. The reply to tool calls is ONE user message holding only tool_result blocks, in call order.
  3. Every stop is a named status in the log, never a silent exit. Findings already proposed stay.
Stop reasons follow platform.claude.com/docs/en/build-with-claude/handling-stop-reasons (2026-10-05).
"""
import hashlib
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from fia_llm.errors import FatalLLMError
from fia_tools.framework import envelope_json

from .kill import KillSwitch
from .limits import Limits, RunState, check_limits
from .runlog import RunLog

NUDGE = ("You have not called finish_review. If you have finished, call finish_review with your summary now. "
         "If you have more to check, make your next tool call.")


@dataclass
class RunResult:
    run_id: str
    status: str                 # finished, or the reason the run stopped early
    detail: str
    calls: int
    tool_calls: int
    findings: int               # propose_finding calls that succeeded
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None    # None when a model has no verified price
    wall_s: float
    finish: dict | None         # the finish_review payload, if the run got that far

    @property
    def finished(self):
        return self.status == "finished"


def _git_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parent, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


def _db_down(ctx):
    return bool(getattr(ctx.conn, "closed", False))


def run_agent(client, registry, ctx, system, task, limits=None, log=None, kill=None,
              thinking=None, effort=None, clock=time.monotonic):
    limits = limits or Limits()
    log = log or RunLog()
    kill = kill or KillSwitch()
    state, t0 = RunState(), clock()
    tools = registry.definitions()
    messages = [{"role": "user", "content": task}]
    tool_calls = findings = bad_streak = nudges = 0
    truncated = False
    max_tokens = limits.max_output_tokens

    log.event("run_start", run_id=ctx.run_id, agent=ctx.agent, dry_run=ctx.dry_run, git_commit=_git_commit(),
              provider=client.provider, alias=client.profile.alias, model=client.profile.model_id,
              thinking=thinking, effort=effort, limits=limits.__dict__,
              system_sha256=hashlib.sha256(system.encode()).hexdigest()[:16], tools=registry.names())

    def end(status, detail=""):
        state.elapsed_s = clock() - t0
        res = RunResult(ctx.run_id, status, detail, state.calls, tool_calls, findings, state.input_tokens,
                        state.output_tokens, state.cost_usd if state.cost_known else None,
                        round(state.elapsed_s, 2), ctx.finish)
        log.event("run_end", status=status, detail=detail, calls=res.calls, tool_calls=tool_calls,
                  findings=findings, input_tokens=res.input_tokens, output_tokens=res.output_tokens,
                  cost_usd=res.cost_usd, cost_known=state.cost_known, wall_s=res.wall_s, finish=ctx.finish)
        return res

    while True:
        state.elapsed_s = clock() - t0
        stop = check_limits(state, limits, kill.is_set())
        if stop:
            return end(stop, kill.reason() or "" if stop == "killed" else "")
        if _db_down(ctx):
            return end("db_error", "database connection is closed")

        started = clock()
        try:
            reply = client.complete(system, messages, tools, max_tokens=max_tokens, thinking=thinking, effort=effort)
        except FatalLLMError as e:
            return end("llm_fatal", str(e))
        state.add(reply)
        log.event("llm_call", call=state.calls, request_id=reply.request_id, workspace_id=reply.workspace_id,
                  stop_reason=reply.stop_reason, input_tokens=reply.usage.input_tokens,
                  cache_read_tokens=reply.usage.cache_read_tokens, cache_write_tokens=reply.usage.cache_write_tokens,
                  output_tokens=reply.usage.output_tokens, cost_usd=reply.cost_usd, settings=reply.settings,
                  latency_s=round(clock() - started, 3), text=reply.text, thinking=reply.thinking,
                  tool_use=[c.name for c in reply.tool_calls])
        stop_reason = reply.stop_reason

        if stop_reason == "max_tokens":          # cut off mid-reply: retry the same request once, bigger
            if truncated:
                return end("output_truncated", f"reply cut off twice at {max_tokens} tokens")
            truncated, max_tokens = True, max_tokens * 2
            log.event("retry_truncated", new_max_tokens=max_tokens)
            continue
        truncated, max_tokens = False, limits.max_output_tokens

        if reply.content:                        # an empty reply is not appended (the API rejects empty content)
            messages.append(reply.assistant_message())

        if stop_reason == "tool_use":
            ctx.calls_used, ctx.calls_allowed = state.calls, limits.max_calls   # shown to the model in each tool result
            results = []
            for call in reply.tool_calls:
                if kill.is_set():
                    return end("killed", kill.reason() or "")
                if _db_down(ctx):
                    return end("db_error", "database connection is closed")
                t = clock()
                env = registry.run(ctx, call.name, call.input)
                tool_calls += 1
                ok = env["ok"]
                findings += ok and call.name == "propose_finding"
                code = None if ok else env["error"]["code"]
                bad_streak = bad_streak + 1 if code == "internal" else 0
                log.event("tool_call", call=state.calls, tool_use_id=call.id, name=call.name,
                          reason=(call.input or {}).get("reason"), args=call.input, ok=ok, error_code=code,
                          row_count=env.get("row_count"), truncated=env.get("truncated"),
                          latency_s=round(clock() - t, 3), result=env)
                block = {"type": "tool_result", "tool_use_id": call.id, "content": envelope_json(env)}
                if not ok:
                    block["is_error"] = True
                results.append(block)
                if bad_streak >= limits.max_internal_errors_in_row:
                    return end("tool_failure", f"{bad_streak} internal tool errors in a row (database down?)")
            if ctx.finished:
                return end("finished")
            messages.append({"role": "user", "content": results})
            continue

        if stop_reason == "end_turn":
            if ctx.finished:
                return end("finished")
            if nudges >= limits.max_nudges:
                return end("no_finish", "the model ended its turn without calling finish_review")
            nudges += 1
            log.event("nudge", count=nudges)
            messages.append({"role": "user", "content": NUDGE})
            continue

        if stop_reason == "refusal":
            return end("refusal", "the model declined to continue")
        if stop_reason == "model_context_window_exceeded":
            return end("context_exceeded", "the conversation filled the model's context window")
        return end("protocol_error", f"unexpected stop_reason {stop_reason!r}")
