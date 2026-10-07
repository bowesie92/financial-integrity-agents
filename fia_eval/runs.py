"""Read one saved run (the JSONL log written by the loop) into a Run the scorer can use. Nothing here
touches the database. A dry run and a real run leave the same log, so both can be scored."""
import json
from dataclasses import dataclass, field
from pathlib import Path

FINDING_KEYS = ("risk", "title", "population", "test_procedure", "criteria", "finding_condition", "cause",
                "effect", "recommendation", "evidence")
TEXT_KEYS = ("title", "population", "test_procedure", "criteria", "finding_condition", "cause", "effect",
             "recommendation")


@dataclass
class Run:
    run_id: str
    agent: str
    alias: str = ""
    findings: list = field(default_factory=list)      # the arguments of each propose_finding that succeeded
    calls: list = field(default_factory=list)         # every tool call: name, args, ok
    offered_tools: list = field(default_factory=list)
    end: dict = field(default_factory=dict)           # the run_end event (status, cost, tokens, finish)
    tool_text: str = ""                               # every tool result, as text, for number grounding
    raw_text: str = ""                                # the whole log, for the secrets scan
    source: str = "log"


def finding_text(f):
    return "\n".join(str(f.get(k) or "") for k in TEXT_KEYS)


def load_run(path):
    raw = Path(path).read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw.splitlines() if line.strip()]
    start = next((e for e in events if e.get("event") == "run_start"), {})
    run = Run(run_id=start.get("run_id") or Path(path).stem, agent=start.get("agent", ""), alias=start.get("alias", ""),
              offered_tools=list(start.get("tools") or []), raw_text=raw)
    run.end = next((e for e in reversed(events) if e.get("event") == "run_end"), {})
    results = []
    for e in events:
        if e.get("event") != "tool_call":
            continue
        run.calls.append({"name": e.get("name"), "args": e.get("args") or {}, "ok": bool(e.get("ok"))})
        results.append(json.dumps(e.get("result"), ensure_ascii=False, default=str))
        if e.get("name") == "propose_finding" and e.get("ok"):
            run.findings.append({k: (e.get("args") or {}).get(k) for k in FINDING_KEYS})
    run.tool_text = "\n".join(results)
    return run


def run_from_findings(run_id, agent, findings, source="memo"):
    """A Run built from findings alone (no tool calls), for previews and tests."""
    return Run(run_id=run_id, agent=agent, findings=list(findings), source=source)
