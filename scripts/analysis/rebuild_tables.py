"""Rebuild the headline results tables from the committed files in results/. No database, no API key, no cost.

    python scripts/analysis/rebuild_tables.py
    python scripts/analysis/rebuild_tables.py --results-dir results

This proves the published tables follow from the committed scored runs. It does not prove the scored runs
themselves are right: that rests on the answer key, the scorer (fia_eval/score.py) and the run logs.
"""
import argparse
import json
from pathlib import Path

GL_PATTERNS = ("round_dollar_cluster", "after_hours_postings", "post_close_thin_description",
               "unusual_user_account", "benford_violation")
SETS = [  # (label, file)
    ("Seed 2, Sonnet 5.5, frozen prompts", "eval_seed2.json"),
    ("Seed 3, Sonnet 5.5, frozen prompts", "eval_seed3_old.json"),
    ("Seed 3, Sonnet 5.5, general prompts", "eval_seed3_new.json"),
    ("Seed 3, Haiku 4.5, frozen prompts", "eval_seed3_haiku.json"),
]
SONNET_SETS = SETS[:3]
RED_TEAM_FILES = ["eval_redteam_seed1.json", "eval_redteam_seed2.json"]


def load(path):
    return json.loads(Path(path).read_text())


def split(records):
    return ([r for r in records if r["agent"] == "ap_guardian"],
            [r for r in records if r["agent"] == "gl_sentinel"])


def pct(a, b):
    return "n/a" if not b else f"{100 * a / b:.0f}%"


def ap_found(r):
    """Planted AP items found and available, for the patterns that have a per-run target (use tax is scored apart)."""
    got = sum(c["found"] for c in r["patterns"].values() if c.get("required"))
    total = sum(c["total"] for c in r["patterns"].values() if c.get("required"))
    return got, total


def decoys(rs):
    return (sum(r["decoys"]["total"] - r["decoys"]["flagged"] for r in rs), sum(r["decoys"]["total"] for r in rs))


def costs(rs):
    c = [float(r["cost"]["cost_usd"]) for r in rs if r["cost"].get("cost_usd") not in (None, "")]
    return c


def money(c):
    return "n/a" if not c else f"${sum(c) / len(c):.2f} (range ${min(c):.2f} to ${max(c):.2f}, {len(c)} runs)"


def injection(rs):
    """Injected-text cases: how many reached the agent, were reported, and were likely obeyed (among those seen)."""
    items = [i for r in rs for i in r["redteam"]["items"]]
    seen = [i for i in items if i["seen_in_tool_results"]]
    return {"cases": len(items), "seen": len(seen), "reported": sum(i["reported"] for i in items),
            "obeyed_seen": sum(bool(i["likely_complied"]) for i in seen),
            "obeyed_all": sum(bool(i["likely_complied"]) for i in items)}


def grounding(rs):
    s = [r["integrity"]["numeric_grounding"]["share"] for r in rs
         if r.get("integrity") and r["integrity"].get("numeric_grounding", {}).get("share") is not None]
    return s


def gl_detected(gl):
    runs = {p: [r["patterns"][p]["found"] >= 1 for r in gl if p in r["patterns"]] for p in GL_PATTERNS}
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--results-dir", default="results")
    d = Path(ap.parse_args().results_dir)
    data = {}
    for label, name in SETS:
        if (d / name).exists():
            data[name] = (label, *split(load(d / name)))

    print("# Results rebuilt from committed files\n")
    print("## Per set\n")
    print("| Set | AP items found | AP decoys cleared | GL pattern-runs found | GL decoys cleared |")
    print("| --- | --- | --- | --- | --- |")
    for name, (label, apr, glr) in data.items():
        g = sum(sum(v) for v in gl_detected(glr).values())
        gt = sum(len(v) for v in gl_detected(glr).values())
        fa, ft = (sum(ap_found(r)[0] for r in apr), sum(ap_found(r)[1] for r in apr))
        da, dt = decoys(apr)
        ga, gtot = decoys(glr)
        print(f"| {label} ({len(apr)} AP, {len(glr)} GL runs) | {fa} of {ft} ({pct(fa, ft)}) | {da} of {dt} ({pct(da, dt)}) "
              f"| {g} of {gt} | {ga} of {gtot} ({pct(ga, gtot)}) |")

    print("\n## Cost per review\n")
    print("| Set | AP | GL |")
    print("| --- | --- | --- |")
    for name, (label, apr, glr) in data.items():
        print(f"| {label} | {money(costs(apr))} | {money(costs(glr))} |")
    s_ap = [r for n, (_, a, _) in data.items() if n in {s[1] for s in SONNET_SETS} for r in a]
    s_gl = [r for n, (_, _, g) in data.items() if n in {s[1] for s in SONNET_SETS} for r in g]
    print(f"| Sonnet 5.5, seeds 2 and 3 combined | {money(costs(s_ap))} | {money(costs(s_gl))} |")

    print("\n## Injected-text cases in ordinary runs (AP runs only)\n")
    print("| Set | Cases | Reached the agent | Reported | Likely obeyed (of those reached) | Likely obeyed (all cases, scorer artifact possible) |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, (label, apr, _) in data.items():
        j = injection(apr)
        print(f"| {label} | {j['cases']} | {j['seen']} | {j['reported']} | {j['obeyed_seen']} | {j['obeyed_all']} |")

    print("\n## GL patterns found, by run\n")
    print("| Set | " + " | ".join(GL_PATTERNS) + " |")
    print("| --- |" + " --- |" * len(GL_PATTERNS))
    for name, (label, _, glr) in data.items():
        det = gl_detected(glr)
        print(f"| {label} | " + " | ".join(f"{sum(v)} of {len(v)}" for v in det.values()) + " |")
    allgl = [r for n, (_, _, g) in data.items() if n in {s[1] for s in SONNET_SETS} for r in g]
    det = gl_detected(allgl)["unusual_user_account"]
    print(f"\nUnusual-account pattern, all Sonnet 5.5 GL runs (seed 2 plus both seed 3 sets): {sum(det)} of {len(det)}")

    every = [r for _, (_, a, g) in data.items() for r in a + g]
    for label, runs in (("Sonnet 5.5 runs", s_ap + s_gl), ("all four sets, both models", every)):
        g = grounding(runs)
        if g:
            print(f"\nNumber grounding, {label}: mean {100 * sum(g) / len(g):.0f}%, "
                  f"range {100 * min(g):.0f}% to {100 * max(g):.0f}% ({len(g)} runs with figures)")

    print("\n## Targeted red-team runs\n")
    for name in RED_TEAM_FILES:
        if (d / name).exists():
            rs = load(d / name)
            for r in rs:
                rt = r["redteam"]
                print(f"- {name} ({r.get('alias') or 'model not recorded'}): reported {rt['reported']} of {rt['total']}, "
                      f"likely complied {rt['likely_complied']}")


if __name__ == "__main__":
    main()
