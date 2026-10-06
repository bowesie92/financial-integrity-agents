"""Run the rules-only baseline and write its findings to a JSON file. No LLM, no cost, no writes to
the database (the agent role cannot write anything but findings, and this never inserts).

    python -m baseline.run --version v2 --label seed1 --out results/baseline_v2_seed1.json
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fia_tools.db import agent_connection
from fia_tools.framework import ToolContext

from . import rules


def run(label, version="v1"):
    conn = agent_connection()
    try:
        ctx = ToolContext(conn=conn, run_id=f"baseline-{version}-{label}", agent="baseline", dry_run=True)
        thresholds = rules.use_version(version)
        findings = rules.run_all(ctx)
    finally:
        conn.close()
    return {"label": label, "version": version, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "thresholds": thresholds,
            "counts": {r: Counter(f["rule"] for f in findings).get(r, 0) for r in rules.ALL_RULES},
            "findings": findings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="name for this run, e.g. seed1")
    ap.add_argument("--version", choices=sorted(rules.VERSIONS), default="v1",
                    help="v1 = thresholds as written in Phase 1; v2 = with Amendment 1")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    result = run(a.label, a.version)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str))
    print(f"{a.version}: {len(result['findings'])} findings -> {out}")
    for rule, n in result["counts"].items():
        print(f"  {rule:22s} {n}")


if __name__ == "__main__":
    main()
