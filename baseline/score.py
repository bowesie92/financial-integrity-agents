"""Score a baseline results file against the ground-truth manifest (fia_gt.manifest, admin role only).
A finding matches a manifest row when they share a journal entry id or an invoice id. The Benford
rule is population-level, so it matches the planted Benford row by quarter. 4.9 builds the full
evaluation harness; this is the same arithmetic for the baseline alone, so the baseline number
exists before any agent does.

    python -m baseline.score --results results/baseline_seed1.json --seed 1
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

PLANTED_BENFORD_QUARTER = "2025-Q3"      # docs/scope.md: the Q3 violation
ID_KEYS = ("je_ids", "invoice_ids")
NO_RULE = {"use_tax_exposure"}           # the baseline has no rule for these, so an overlap is coincidence


def ids_of(refs):
    return {x for k in ID_KEYS for x in refs.get(k, [])}


def score(findings, manifest):
    """findings: list from the results file. manifest: rows with kind, agent, pattern, record_refs."""
    by_id = defaultdict(list)
    for i, f in enumerate(findings):
        for x in ids_of(f["refs"]):
            by_id[x].append(i)
    benford_hit = [i for i, f in enumerate(findings)
                   if f["rule"] == "benford" and f["refs"].get("quarter") == PLANTED_BENFORD_QUARTER]
    status = {}                      # finding index -> "planted" | "decoy" | "none"
    patterns = defaultdict(lambda: Counter())
    for m in manifest:
        if m["pattern"] == "benford_violation":
            hits = set(benford_hit)
        elif m["pattern"] in NO_RULE:
            hits = set()
        else:
            hits = {i for x in ids_of(m["record_refs"]) for i in by_id.get(x, [])}
        if m["kind"] == "redteam":
            if m["record_refs"].get("underlying_pattern") is None:
                continue
            key, hit = f"redteam underlying {m['record_refs']['underlying_pattern']}", bool(hits)
        else:
            key, hit = m["pattern"], bool(hits)
        c = patterns[(m["kind"], key)]
        c["total"] += 1
        c["hit"] += hit
        for i in hits:
            if m["kind"] == "planted":
                status[i] = "planted"
            elif m["kind"] == "decoy":
                status.setdefault(i, "decoy")
    rules = defaultdict(Counter)
    for i, f in enumerate(findings):
        rules[f["rule"]][status.get(i, "none")] += 1
        rules[f["rule"]]["total"] += 1
    planted = {k[1]: c for k, c in patterns.items() if k[0] == "planted"}
    decoys = {k[1]: c for k, c in patterns.items() if k[0] == "decoy"}
    redteam = {k[1]: c for k, c in patterns.items() if k[0] == "redteam"}
    tp = sum(c["hit"] for c in planted.values())
    n = sum(c["total"] for c in planted.values())
    n_rule = sum(c["total"] for p, c in planted.items() if p not in NO_RULE)
    dh = sum(c["hit"] for c in decoys.values())
    dn = sum(c["total"] for c in decoys.values())
    return {
        "planted": {p: {"found": c["hit"], "total": c["total"], "recall": round(c["hit"] / c["total"], 3)}
                    for p, c in sorted(planted.items())},
        "decoys": {p: {"flagged": c["hit"], "total": c["total"], "cleared": round(1 - c["hit"] / c["total"], 3)}
                   for p, c in sorted(decoys.items())},
        "redteam": {p: {"found": c["hit"], "total": c["total"]} for p, c in sorted(redteam.items())},
        "rules": {r: {"findings": c["total"], "planted": c["planted"], "decoy": c["decoy"], "unmatched": c["none"],
                      "precision": round(c["planted"] / c["total"], 3)} for r, c in sorted(rules.items())},
        "overall": {"planted_recall": round(tp / n, 3) if n else None,
                    "planted_recall_where_a_rule_exists": round(tp / n_rule, 3) if n_rule else None, "decoy_clearance": round(1 - dh / dn, 3) if dn else None,
                    "findings": len(findings)},
    }


def render(s):
    lines = ["PLANTED (recall by pattern)"]
    lines += [f"  {p:34s} {v['found']:3d}/{v['total']:<3d} {v['recall']:.2f}" + ("  (no rule)" if p in NO_RULE else "")
              for p, v in s["planted"].items()]
    lines += ["DECOYS (share cleared, higher is better)"]
    lines += [f"  {p:34s} flagged {v['flagged']:3d}/{v['total']:<3d} cleared {v['cleared']:.2f}" for p, v in s["decoys"].items()]
    lines += ["RED TEAM (underlying anomaly found by a rule)"]
    lines += [f"  {p:34s} {v['found']}/{v['total']}" for p, v in s["redteam"].items()]
    lines += ["RULES (precision = findings that hit a planted row)"]
    lines += [f"  {r:22s} findings {v['findings']:3d}  planted {v['planted']:3d}  decoy {v['decoy']:3d}  "
              f"unmatched {v['unmatched']:3d}  precision {v['precision']:.2f}" for r, v in s["rules"].items()]
    o = s["overall"]
    lines += [f"OVERALL planted recall {o['planted_recall']} (excluding patterns with no rule "
              f"{o['planted_recall_where_a_rule_exists']})  decoy clearance {o['decoy_clearance']}  findings {o['findings']}"]
    return "\n".join(lines)


def admin_connection():
    import psycopg
    dsn = os.environ.get("FIA_ADMIN_DSN")
    if dsn:
        return psycopg.connect(dsn, autocommit=True)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from setup_fia_roles import connect, load
    env = load()
    return connect(env, "fia_admin", env["SUPABASE_FIA_ADMIN_PASSWORD"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--json-out")
    a = ap.parse_args()
    from psycopg.rows import dict_row
    res = json.loads(Path(a.results).read_text())
    conn = admin_connection()
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("select kind, agent, pattern, record_refs from fia_gt.manifest where seed = %s", [a.seed])
        manifest = cur.fetchall()
    conn.close()
    if not manifest:
        sys.exit(f"No manifest rows for seed {a.seed}. Is that seed the one loaded?")
    s = score(res["findings"], manifest)
    print(render(s))
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
