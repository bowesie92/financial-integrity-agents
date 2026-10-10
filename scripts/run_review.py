"""Run one review by GL Sentinel or AP Guardian and write the memo and a readable transcript.

Usage (from the repo root, venv active):
  python scripts/run_review.py --agent ap --dry-run     nothing is stored; the memo is built from the log
  python scripts/run_review.py --agent ap               real run: findings are stored, the memo is built from them
  python scripts/run_gl_sentinel.py ...                 the same as --agent gl

Options: --agent gl|ap (default gl)  --model dev|demo|demo-plus (default dev, Haiku 4.5)  --prompt VERSION
         --max-calls N  --max-cost USD  --max-wall SECONDS  --no-cache
         --task-file PATH   (use the text in that file as the task instead of the standard one, for the red-team run)
         --env-file PATH  --key-var NAME   (where and under what name the Anthropic key is saved)

The key is read from the env file and never printed. Files written: runs/<run_id>.jsonl (the log),
runs/<run_id>.txt (the transcript), memos/<run_id>.md (the memo). To stop a run early:
  touch .fia_kill      or press Ctrl+C once.
"""
import os
import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fia_agents import ap_guardian, gl_sentinel  # noqa: E402
from fia_agents.kill import KillSwitch  # noqa: E402
from fia_agents.limits import Limits  # noqa: E402
from fia_agents.memo import findings_for_run, findings_from_log, render_document  # noqa: E402
from fia_agents.transcript import transcript_from_log  # noqa: E402
from fia_llm import AnthropicClient, get_profile  # noqa: E402
from fia_tools.db import agent_connection  # noqa: E402

AGENTS = {"gl": gl_sentinel, "ap": ap_guardian}


def read_key(path, name):
    for line in Path(path).read_text().splitlines():
        m = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip("'\"")
    raise SystemExit(f"{name} not found in {path}. Pass --key-var with the variable name used in that file.")


def parse(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="gl", choices=sorted(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="dev")
    ap.add_argument("--max-calls", type=int, default=Limits().max_calls)
    ap.add_argument("--max-cost", type=Decimal, default=Limits().max_cost_usd)
    ap.add_argument("--max-wall", type=float, default=Limits().max_wall_s)
    ap.add_argument("--prompt", default=None, help="system prompt version (default: the agent's current one)")
    ap.add_argument("--no-cache", action="store_true", help="turn prompt caching off")
    ap.add_argument("--task-file", default=None, help="a text file holding the task (default: the agent's standard task)")
    ap.add_argument("--env-file", default=os.path.join(os.environ.get("FIA_SECRETS_DIR", "/etc/financial-integrity-agents-secrets"), "anthropic.env"))
    ap.add_argument("--key-var", default="ANTHROPIC_API_KEY")
    a = ap.parse_args(argv)
    mod = AGENTS[a.agent]
    a.prompt = a.prompt or mod.PROMPT_VERSION
    if a.prompt not in mod.TEMPLATES:
        ap.error(f"--prompt {a.prompt} is not a prompt of agent {a.agent}. Known: {', '.join(sorted(mod.TEMPLATES))}")
    a.task = None
    if a.task_file:
        path = Path(a.task_file)
        if not path.is_file():
            ap.error(f"--task-file {a.task_file} does not exist")
        a.task = path.read_text(encoding="utf-8").strip()
        if not a.task:
            ap.error(f"--task-file {a.task_file} is empty")
    return a, mod


def main(argv=None):
    a, mod = parse(argv)
    limits = Limits(max_calls=a.max_calls, max_cost_usd=a.max_cost, max_wall_s=a.max_wall)
    client = AnthropicClient(get_profile(a.model), api_key=read_key(a.env_file, a.key_var), cache=not a.no_cache)
    run_id = mod.new_run_id()
    kill = KillSwitch()
    if kill.is_set():
        raise SystemExit(f"A stop signal is already set ({kill.reason()}). Remove the file {kill.path} first.")
    kill.install_signals()
    conn = agent_connection()
    print(f"Starting {run_id} on {a.model}, prompt {a.prompt} ({'dry run' if a.dry_run else 'REAL RUN, findings will be stored'}). "
          f"Limits: {limits.max_calls} calls, ${limits.max_cost_usd}, {limits.max_wall_s:.0f} s. Stop with: touch .fia_kill")
    if a.task:
        print(f"Task read from {a.task_file} ({len(a.task)} characters), not the standard task.")
    try:
        result, log_path = mod.run_review(client, conn, run_id=run_id, dry_run=a.dry_run, limits=limits,
                                          log_dir=ROOT / "runs", kill=kill, prompt_version=a.prompt, task=a.task)
        if a.dry_run:
            findings, source = findings_from_log(log_path), "run log (dry run, nothing stored)"
        else:
            findings, source = findings_for_run(conn, run_id, agent=mod.AGENT), "database"
    finally:
        kill.restore_signals()
        conn.close()

    memo_dir = ROOT / "memos"
    memo_dir.mkdir(exist_ok=True)
    memo_path = memo_dir / f"{run_id}.md"
    memo_path.write_text(render_document(result, findings, a.model, source, a.prompt, agent=mod.AGENT), encoding="utf-8")
    txt_path = log_path.with_suffix(".txt")
    txt_path.write_text(transcript_from_log(log_path), encoding="utf-8")

    cost = "not priced" if result.cost_usd is None else f"${result.cost_usd:.4f}"
    print(f"\nstatus {result.status}  calls {result.calls}  tool calls {result.tool_calls}  findings {result.findings}  "
          f"tokens {result.input_tokens}/{result.output_tokens}  cost {cost}  time {result.wall_s} s")
    reads = writes = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("event") == "llm_call":
            reads += e.get("cache_read_tokens") or 0
            writes += e.get("cache_write_tokens") or 0
    print(f"cache     {'off' if a.no_cache else 'on'}  read {reads}  written {writes}  (the input figure above includes both)")
    if result.detail:
        print("detail:", result.detail)
    print("log       ", log_path.relative_to(ROOT))
    print("transcript", txt_path.relative_to(ROOT))
    print("memo      ", memo_path.relative_to(ROOT))
    return 0 if result.finished else 2


if __name__ == "__main__":
    sys.exit(main())
