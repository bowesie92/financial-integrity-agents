"""Count tool calls by tool name for every local run log, with rows returned, errors and cut-off results.
Run from the repo root: python scripts/analysis/tool_mix.py
Writes results/analysis/tool_mix.csv. Needs the local runs/ folder, which is not published."""
import csv, glob, json, collections, os

os.makedirs("results/analysis", exist_ok=True)
out = csv.writer(open("results/analysis/tool_mix.csv", "w", newline=""))
out.writerow(["run_id", "agent", "model", "tool", "calls", "rows_returned", "errors", "truncated", "seconds"])
for f in sorted(glob.glob("runs/*.jsonl")):
    start = None
    stats = collections.defaultdict(lambda: [0, 0, 0, 0, 0.0])
    for line in open(f):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "run_start":
            start = e
        elif e.get("event") == "tool_call":
            s = stats[e.get("name")]
            s[0] += 1
            s[1] += e.get("row_count") or 0
            s[2] += 0 if e.get("ok") else 1
            s[3] += 1 if e.get("truncated") else 0
            s[4] += e.get("latency_s") or 0
    if start is None:
        continue
    for name, s in sorted(stats.items(), key=lambda kv: str(kv[0])):
        out.writerow([start.get("run_id"), start.get("agent"), start.get("model"), name, s[0], s[1], s[2], s[3], round(s[4], 1)])
print("wrote results/analysis/tool_mix.csv")
