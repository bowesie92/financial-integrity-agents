"""Search the whole git history for the exact values of your real secrets, without ever printing them.
Reads every KEY=value line from the env files you name (default: the secrets folder), then asks, with hidden
input, for any extra values such as the Discord webhook URL. Prints only the variable name and where a match
was found. Run from the repo root: python scripts/audit_secret_values.py [file.env ...]"""
import getpass, glob, re, subprocess, sys, urllib.parse

def git(*a):
    return subprocess.run(["git", *a], capture_output=True).stdout

secrets = {}
files = sys.argv[1:] or sorted(glob.glob("/etc/financial-integrity-agents-secrets/*.env"))
skipped = []
for f in files:
    for line in open(f, errors="ignore"):
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip("'\"")
        if len(val) < 8:
            skipped.append(name)
            continue
        secrets[f.split("/")[-1] + ":" + name] = val
n = 0
while True:
    n += 1
    v = getpass.getpass(f"Extra secret {n} (hidden, press Enter alone to finish): ")
    if not v.strip():
        break
    secrets[f"extra-{n}"] = v.strip()

needles = {}
for name, val in secrets.items():
    forms = {val, urllib.parse.quote(val, safe="")}
    m = re.match(r"^[a-z][a-z0-9+.\-]*://[^:/@\s]+:([^@\s]+)@", val)
    if m and len(m.group(1)) >= 8:
        forms.add(m.group(1))
    needles[name] = [f.encode() for f in forms]

objs = git("rev-list", "--objects", "--all").decode("utf-8", "ignore").splitlines()
paths = {}
for line in objs:
    p = line.split(" ", 1)
    if len(p) == 2 and p[0] not in paths:
        paths[p[0]] = p[1]
types = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype)"],
                       input="\n".join(paths).encode(), capture_output=True).stdout.decode().splitlines()
blobs = [t.split()[0] for t in types if t.split()[1] == "blob"]
found = {k: [] for k in secrets}
for s in blobs:
    data = git("cat-file", "blob", s)
    for name, forms in needles.items():
        if any(f in data for f in forms):
            found[name].append(f"{paths[s]} @ {s[:8]}")
msgs = git("log", "--all", "--format=%B")
for name, forms in needles.items():
    if any(f in msgs for f in forms):
        found[name].append("a commit message")
print(f"checked {len(secrets)} secret value(s) against {len(blobs)} file versions and all commit messages")
if skipped:
    print("skipped as too short to search safely:", ", ".join(skipped))
bad = 0
for name, where in found.items():
    if where:
        bad += 1
        print(f"FOUND  {name}: " + "; ".join(sorted(set(where))[:10]))
    else:
        print(f"clean  {name}")
print("RESULT:", "SECRET VALUES ARE IN THE HISTORY" if bad else "none of the values appear anywhere in the history")
sys.exit(1 if bad else 0)
