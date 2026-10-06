"""Turn findings into memos in the format of docs/memo_template.md.

A finding is a dict with the same keys as the columns of fia.findings. For a real run the findings
come from the database (the stored row is the source of truth). For a dry run nothing is stored, so
they come from the run log. The memo text is built by this code from those fields; no model writes
the memo layout, and no number in it is computed here."""
import json
from pathlib import Path

from fia_tools.db import query

FIELDS = (("Risk", "risk"), ("Population", "population"), ("Procedure", "test_procedure"),
          ("Criteria", "criteria"), ("Condition", "finding_condition"), ("Cause", "cause"),
          ("Effect", "effect"), ("Recommendation", "recommendation"))
COLUMNS = ("finding_id", "run_id", "agent", "risk", "title", "population", "test_procedure", "criteria",
           "finding_condition", "cause", "effect", "recommendation", "evidence", "created_at")


def findings_for_run(conn, run_id, agent="gl_sentinel"):
    """Stored findings for one run, oldest first. The agent role may read fia.findings."""
    return query(conn, "select " + ", ".join(COLUMNS) + " from fia.findings where run_id = %s and agent = %s "
                 "order by created_at, title", (run_id, agent))


def findings_from_events(events):
    """Findings the model proposed successfully, read from run log events (used for dry runs)."""
    out = []
    for e in events:
        if e.get("event") == "tool_call" and e.get("name") == "propose_finding" and e.get("ok"):
            a = e.get("args") or {}
            out.append({k: a.get(k) for k in COLUMNS if k in a})
    return out


def read_events(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def findings_from_log(path):
    return findings_from_events(read_events(path))


def _evidence_lines(evidence):
    by_table, notes = {}, []
    for item in evidence or []:
        by_table.setdefault(item["table"], []).append(item["id"])
        if item.get("note"):
            notes.append(f"  - {item['table']} {item['id']}: {item['note']}")
    line = "; ".join(f"{t} {', '.join(ids)}" for t, ids in by_table.items())
    return "**Evidence:** " + line + ("\n" + "\n".join(notes) if notes else "")


def render_memo(f, number=None):
    head = f"### {number}. {f['title']}" if number else f"### {f['title']}"
    body = [head, ""]
    for label, key in FIELDS:
        body.append(f"**{label}:** {f.get(key) or 'Not stated'}")
    body.append(_evidence_lines(f.get("evidence")))
    return "\n".join(body)


def render_document(result, findings, model_alias="", source="database", prompt_version=""):
    """The whole review as markdown: header, summary, every memo, then what was and was not checked."""
    fin = result.finish or {}
    cost = "not priced" if result.cost_usd is None else f"${result.cost_usd:.4f}"
    lines = [f"# GL Sentinel review {result.run_id}", "",
             f"Status: {result.status}. Model calls: {result.calls}. Tool calls: {result.tool_calls}. "
             f"Findings proposed: {result.findings}. Tokens in/out: {result.input_tokens}/{result.output_tokens}. "
             f"Cost: {cost}. Time: {result.wall_s} s."]
    if model_alias or prompt_version:
        lines.append(f"Model alias: {model_alias or 'unknown'}. Prompt version: {prompt_version or 'unknown'}. "
                     f"Findings read from the {source}.")
    if not result.finished:
        lines += ["", f"**INCOMPLETE RUN.** The run stopped with status {result.status}"
                  f"{': ' + result.detail if result.detail else ''}. Findings below were proposed before the stop; "
                  "nothing after it was tested."]
    lines += ["", "Every item below is a proposal for a person to review. Nothing was posted, changed or paid.", ""]
    if fin.get("summary"):
        lines += ["## Summary", "", fin["summary"], ""]
    lines += [f"## Findings ({len(findings)})", ""]
    if not findings:
        lines += ["No findings were proposed.", ""]
    for i, f in enumerate(findings, 1):
        lines += [render_memo(f, i), ""]
    lines += ["## Checked", ""] + [f"- {x}" for x in fin.get("checked", [])] + [""]
    nc = fin.get("not_checked") or []
    lines += ["## Not checked in this run", ""] + ([f"- {x}" for x in nc] if nc else ["- Nothing was listed by the model."]) + [""]
    return "\n".join(lines)
