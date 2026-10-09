"""For each GL run scored on seed 3, check whether each planted journal entry id ever appeared in a tool result
the agent received, and whether it appeared in a proposed finding. Needs the local runs/ folder (not published).
Run from the repo root: python scripts/analysis/gl_seen.py. Writes results/analysis/gl_seen.csv."""
import csv, glob, json, collections, os

os.makedirs("results/analysis", exist_ok=True)
planted = collections.defaultdict(list)
for r in csv.DictReader(open("data/generated/seed3/manifest.csv")):
    if r["agent"] == "gl_sentinel" and r["kind"] == "planted":
        planted[r["pattern"]] += json.loads(r["record_refs"]).get("je_ids", [])
logs = {}
for f in glob.glob("runs/*.jsonl"):
    res, args, rid = [], [], None
    for line in open(f):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("event") == "run_start":
            rid = e.get("run_id")
        elif e.get("event") == "tool_call":
            res.append(json.dumps(e.get("result"), default=str))
            if e.get("name") == "propose_finding":
                args.append(json.dumps(e.get("args"), default=str))
    if rid:
        logs[rid] = ("\n".join(res), "\n".join(args))
out = csv.writer(open("results/analysis/gl_seen.csv", "w", newline=""))
out.writerow(["file", "run_id", "pattern", "planted", "seen_in_tool_results", "in_proposals", "unseen_ids"])
for f in ["eval_seed3_old", "eval_seed3_new", "eval_seed3_haiku"]:
    for r in json.load(open("results/%s.json" % f)):
        rid = r.get("run_id")
        if r.get("agent") != "gl_sentinel" or rid not in logs:
            continue
        res, args = logs[rid]
        for pat, ids in planted.items():
            seen = [i for i in ids if i in res]
            prop = [i for i in ids if i in args]
            out.writerow([f, rid, pat, len(ids), len(seen), len(prop), " ".join(i for i in ids if i not in res)])
print("wrote results/analysis/gl_seen.csv")
