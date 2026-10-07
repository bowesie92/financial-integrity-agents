"""Score named agent runs against the ground-truth manifest (metrics.md). Reads only the run logs you name.

    python scripts/evaluate.py --runs runs/ap-20261007-000915-9c27f4.jsonl --seed 1
    python scripts/evaluate.py --runs runs/a.jsonl runs/b.jsonl --seed 1 --json-out results/eval_seed1.json
    python scripts/evaluate.py --runs runs/a.jsonl --seed 1 --offline     (no database; rebuilds the data from the seed)

Needs the admin database role (the same one the baseline scorer uses), unless --offline is given."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fia_eval.lookups import DbLookups, GeneratorLookups          # noqa: E402
from fia_eval.report import render_all                            # noqa: E402
from fia_eval.runs import load_run                                # noqa: E402
from fia_eval.score import score_run                              # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="run log files (runs/<run id>.jsonl)")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--json-out")
    ap.add_argument("--offline", action="store_true", help="rebuild the data from the seed instead of using the database")
    ap.add_argument("--sample-seed", type=int, default=2026)
    a = ap.parse_args()
    runs = [load_run(p) for p in a.runs]
    if a.offline:
        from generator.build import build
        ds = build(a.seed)
        manifest, lookups, conn = ds.manifest, GeneratorLookups(ds), None
    else:
        from baseline.score import admin_connection
        from psycopg.rows import dict_row
        conn = admin_connection()
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select kind, agent, pattern, severity, record_refs from fia_gt.manifest where seed = %s", [a.seed])
            manifest = cur.fetchall()
        if not manifest:
            sys.exit(f"No manifest rows for seed {a.seed}. Is that seed the one loaded?")
        lookups = DbLookups(conn)
    scores = [score_run(r, manifest, lookups) for r in runs]
    print(render_all(scores, a.sample_seed))
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(scores, indent=1, default=str))
        print(f"\nFull numbers written to {a.json_out}")
    if conn is not None:
        conn.close()


if __name__ == "__main__":
    main()
