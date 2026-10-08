"""Write the task text for the red-team run from the answer key for one seed.

    python scripts/make_redteam_task.py --seed 1 --out results/redteam_task_seed1.txt

Then:  python scripts/run_review.py --agent ap --dry-run --task-file results/redteam_task_seed1.txt
Needs the admin database role (the same one the baseline scorer uses)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fia_eval.redteam import redteam_invoice_ids, redteam_task  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from baseline.score import admin_connection
    from psycopg.rows import dict_row
    conn = admin_connection()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select kind, agent, pattern, severity, record_refs from fia_gt.manifest where seed = %s", [a.seed])
        manifest = cur.fetchall()
    conn.close()
    if not manifest:
        sys.exit(f"No manifest rows for seed {a.seed}. Is that seed the one loaded?")
    text = redteam_task(manifest)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {a.out}: {len(redteam_invoice_ids(manifest))} invoices, {len(text)} characters.")


if __name__ == "__main__":
    main()
