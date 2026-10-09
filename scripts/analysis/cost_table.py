"""Build results/analysis/run_costs.csv from the local run logs in runs/ (one row per run).
Run from the repo root: python scripts/analysis/cost_table.py
The runs/ folder is not published, so this file documents how the cost table was made."""
import csv, glob, json, os

os.makedirs("results/analysis", exist_ok=True)
cols = ["run_id", "start_utc", "agent", "model", "dry_run", "status", "calls", "tool_calls", "findings",
        "fresh_input", "cache_write", "cache_read", "output", "cost_usd", "wall_s"]
out = csv.writer(open("results/analysis/run_costs.csv", "w", newline=""))
out.writerow(cols)
for f in sorted(glob.glob("runs/*.jsonl")):
    ev = []
    for line in open(f):
        try:
            ev.append(json.loads(line))
        except ValueError:
            pass
    start = next((e for e in ev if e.get("event") == "run_start"), None)
    if start is None:
        continue
    end = next((e for e in ev if e.get("event") == "run_end"), {})
    calls = [e for e in ev if e.get("event") == "llm_call"]

    def tot(k):
        return sum(e.get(k) or 0 for e in calls)

    cost = sum(float(e.get("cost_usd") or 0) for e in calls)
    out.writerow([start.get("run_id"), start.get("ts"), start.get("agent"), start.get("model"), start.get("dry_run"),
                  end.get("status", "no_end_event"), len(calls), end.get("tool_calls"), end.get("findings"),
                  tot("input_tokens"), tot("cache_write_tokens"), tot("cache_read_tokens"), tot("output_tokens"),
                  round(cost, 6), end.get("wall_s")])
print("wrote results/analysis/run_costs.csv")
