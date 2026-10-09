"""List every item the scorer marked as missed, per run, from results/*.json.
Item keys are labels such as split_invoices#2, so this cannot link a miss to the run log.
Use gl_seen.py for the check against real journal entry ids.
Run from the repo root: python scripts/analysis/miss_check.py. Writes results/analysis/miss_check.csv."""
import csv, glob, json, os

os.makedirs("results/analysis", exist_ok=True)
out = csv.writer(open("results/analysis/miss_check.csv", "w", newline=""))
out.writerow(["file", "run_id", "agent", "pattern", "key", "closest_finding"])
scored = 0
for f in sorted(glob.glob("results/*.json")):
    try:
        d = json.load(open(f))
    except ValueError:
        continue
    runs = d if isinstance(d, list) else [d]
    for r in runs:
        if not isinstance(r, dict) or "not_found" not in r:
            continue
        scored += 1
        for m in r["not_found"]:
            out.writerow([f.split("/")[-1], r.get("run_id"), r.get("agent"), m.get("pattern"), m.get("key"),
                          m.get("closest_finding")])
print("scored runs:", scored, "| wrote results/analysis/miss_check.csv")
