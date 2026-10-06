"""Run one GL Sentinel review and write the memo and a readable transcript.

Usage (from the repo root, venv active):
  python scripts/run_gl_sentinel.py --dry-run          nothing is stored; the memo is built from the log
  python scripts/run_gl_sentinel.py                    real run: findings are stored, the memo is built from them

Options: --model dev|demo|demo-plus (default dev, Haiku 4.5)  --max-calls N  --max-cost USD  --max-wall SECONDS
         --env-file PATH  --key-var NAME   (where and under what name the Anthropic key is saved)

The key is read from the env file and never printed. Files written: runs/<run_id>.jsonl (the log),
runs/<run_id>.txt (the transcript), memos/<run_id>.md (the memo). To stop a run early:
  touch .fia_kill      or press Ctrl+C once.
"""
import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fia_agents.gl_sentinel import PROMPT_VERSION, new_run_id, run_review  # noqa: E402
from fia_agents.kill import KillSwitch  # noqa: E402
from fia_agents.limits import Limits  # noqa: E402
from fia_agents.memo import findings_for_run, findings_from_log, render_document  # noqa: E402
from fia_agents.transcript import transcript_from_log  # noqa: E402
from fia_llm import AnthropicClient, get_profile  # noqa: E402
from fia_tools.db import agent_connection  # noqa: E402


def read_key(path, name):
    for line in Path(path).read_text().splitlines():
        m = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).strip().strip("'\"")
    raise SystemExit(f"{name} not found in {path}. Pass --key-var with the variable name used in that file.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="dev")
    ap.add_argument("--max-calls", type=int, default=Limits().max_calls)
    ap.add_argument("--max-cost", type=Decimal, default=Limits().max_cost_usd)
    ap.add_argument("--max-wall", type=float, default=Limits().max_wall_s)
    ap.add_argument("--env-file", default="/etc/financial-integrity-agents-secrets/anthropic.env")
    ap.add_argument("--key-var", default="ANTHROPIC_API_KEY")
    a = ap.parse_args()

    limits = Limits(max_calls=a.max_calls, max_cost_usd=a.max_cost, max_wall_s=a.max_wall)
    client = AnthropicClient(get_profile(a.model), api_key=read_key(a.env_file, a.key_var))
    run_id = new_run_id()
    kill = KillSwitch()
    if kill.is_set():
        raise SystemExit(f"A stop signal is already set ({kill.reason()}). Remove the file {kill.path} first.")
    kill.install_signals()
    conn = agent_connection()
    print(f"Starting {run_id} on {a.model} ({'dry run' if a.dry_run else 'REAL RUN, findings will be stored'}). "
          f"Limits: {limits.max_calls} calls, ${limits.max_cost_usd}, {limits.max_wall_s:.0f} s. Stop with: touch .fia_kill")
    try:
        result, log_path = run_review(client, conn, run_id=run_id, dry_run=a.dry_run, limits=limits,
                                      log_dir=ROOT / "runs", kill=kill)
        if a.dry_run:
            findings, source = findings_from_log(log_path), "run log (dry run, nothing stored)"
        else:
            findings, source = findings_for_run(conn, run_id), "database"
    finally:
        kill.restore_signals()
        conn.close()

    memo_dir = ROOT / "memos"
    memo_dir.mkdir(exist_ok=True)
    memo_path = memo_dir / f"{run_id}.md"
    memo_path.write_text(render_document(result, findings, a.model, source, PROMPT_VERSION), encoding="utf-8")
    txt_path = log_path.with_suffix(".txt")
    txt_path.write_text(transcript_from_log(log_path), encoding="utf-8")

    cost = "not priced" if result.cost_usd is None else f"${result.cost_usd:.4f}"
    print(f"\nstatus {result.status}  calls {result.calls}  tool calls {result.tool_calls}  findings {result.findings}  "
          f"tokens {result.input_tokens}/{result.output_tokens}  cost {cost}  time {result.wall_s} s")
    if result.detail:
        print("detail:", result.detail)
    print("log       ", log_path.relative_to(ROOT))
    print("transcript", txt_path.relative_to(ROOT))
    print("memo      ", memo_path.relative_to(ROOT))
    return 0 if result.finished else 2


if __name__ == "__main__":
    sys.exit(main())
