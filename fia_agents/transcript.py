"""Turn a run log (JSONL) into a plain-text transcript a person can read top to bottom."""
import json

from .memo import read_events

SHOW = 400   # characters of each tool result to show


def _clip(text, n=SHOW):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + " ... [cut]"


def render_transcript(events):
    out = []
    for e in events:
        k = e.get("event")
        if k == "run_start":
            out.append(f"RUN {e['run_id']}  agent {e['agent']}  model {e['model']}  dry_run {e['dry_run']}  "
                       f"git {e.get('git_commit')}  system prompt hash {e['system_sha256']}")
            out.append(f"LIMITS {e['limits']}")
        elif k == "llm_call":
            out.append("")
            out.append(f"--- model call {e['call']}  stop {e['stop_reason']}  tokens {e['input_tokens']}/"
                       f"{e['output_tokens']}  cost {e['cost_usd']}  {e['latency_s']} s")
            if e.get("text"):
                out.append("MODEL SAYS: " + _clip(e["text"], 1500))
        elif k == "tool_call":
            out.append(f"TOOL {e['name']}  ok {e['ok']}  rows {e.get('row_count')}  truncated {e.get('truncated')}")
            out.append("  WHY: " + str(e.get("reason")))
            args = {a: v for a, v in (e.get("args") or {}).items() if a != "reason"}
            out.append("  ARGS: " + _clip(json.dumps(args, ensure_ascii=False), 700))
            res = e.get("result") or {}
            out.append("  RESULT: " + _clip(json.dumps(res.get("result", res.get("error")), ensure_ascii=False)))
        elif k == "nudge":
            out.append("NUDGE: reminded the model to call finish_review")
        elif k == "retry_truncated":
            out.append(f"RETRY: reply was cut off, trying again with {e['new_max_tokens']} tokens")
        elif k == "run_end":
            out.append("")
            out.append(f"END status {e['status']}  calls {e['calls']}  tools {e['tool_calls']}  findings {e['findings']}  "
                       f"tokens {e['input_tokens']}/{e['output_tokens']}  cost {e['cost_usd']}  {e['wall_s']} s")
    return "\n".join(out) + "\n"


def transcript_from_log(path):
    return render_transcript(read_events(path))
