"""Read-only scan of every file in every commit of this git repo for secrets and personal data.
Prints where something was found and a redacted preview. Never prints a full value."""
import re, subprocess, sys, collections

def git(*a, raw=False):
    r = subprocess.run(["git", *a], capture_output=True)
    return r.stdout if raw else r.stdout.decode("utf-8", "ignore")

SECRET = {
    "anthropic key": r"sk-ant-[A-Za-z0-9_\-]{16,}",
    "openai-style key": r"\bsk-[A-Za-z0-9]{32,}",
    "jwt": r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    "aws access key id": r"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
    "aws secret key": r"(?i)aws_secret_access_key\s*[=:]\s*\S{20,}",
    "database url with password": r"(?i)\b(postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^:\s/@]+:[^@\s]+@",
    "discord webhook": r"discord(?:app)?\.com/api/webhooks/\d+/[\w\-]+",
    "slack token": r"\bxox[abprs]-[A-Za-z0-9\-]{10,}",
    "github token": r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "mailgun key": r"\bkey-[0-9a-f]{32}\b",
    "private key block": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY",
    "password-like assignment": r"(?i)\b[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY)[A-Z0-9_]*\s*[=:]\s*['\"]?[^\s'\"$<{(\[]{8,}",
}
REVIEW = {
    "supabase project host/ref": r"[a-z0-9]{20}\.supabase\.co|postgres\.[a-z0-9]{20}|aws-\d-[a-z0-9\-]+\.pooler\.supabase\.com",
    "email address": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+\.[A-Za-z0-9.\-]+",
    "ip address": r"\b(?!127\.0\.0\.1\b|0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b",
    "webhook or hook url": r"https?://[^\s'\"]*(?:hooks?|webhook)[^\s'\"]*",
}
SECRET = {k: re.compile(v) for k, v in SECRET.items()}
REVIEW = {k: re.compile(v) for k, v in REVIEW.items()}
BAD_NAMES = re.compile(r"(^|/)(\.env[^/]*|[^/]*\.env|[^/]*\.pem|[^/]*\.key|id_rsa[^/]*|\.fia_kill|[^/]*\.jsonl|secrets?[^/]*)$", re.I)

def redact(s):
    s = s.strip()
    return (s[:4] + "..." + f"({len(s)} chars)") if len(s) > 8 else "(short)"

objs = git("rev-list", "--objects", "--all").splitlines()
paths = {}
for line in objs:
    p = line.split(" ", 1)
    if len(p) == 2 and p[0] not in paths:
        paths[p[0]] = p[1]
shas = list(paths)
types = {}
if shas:
    out = subprocess.run(["git", "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                         input="\n".join(shas).encode(), capture_output=True).stdout.decode().splitlines()
    for l in out:
        s, t, n = l.split()
        types[s] = (t, int(n))
blobs = [s for s in shas if types.get(s, ("", 0))[0] == "blob"]
print(f"commits: {len(git('rev-list','--all').split())}  files (unique versions): {len(blobs)}")

hits = []
review = collections.defaultdict(lambda: collections.defaultdict(set))
for s in blobs:
    path = paths[s]
    if BAD_NAMES.search(path):
        hits.append(("tracked file with a sensitive name", path, s[:8], "(name only)"))
    if types[s][1] > 5_000_000:
        hits.append(("large file (not scanned)", path, s[:8], f"{types[s][1]//1000} KB"))
        continue
    text = git("cat-file", "blob", s, raw=True).decode("utf-8", "ignore")
    for name, rx in SECRET.items():
        for m in rx.finditer(text):
            hits.append((name, path, s[:8], redact(m.group(0))))
            break
    for name, rx in REVIEW.items():
        for m in rx.finditer(text):
            review[name][m.group(0)].add(path)

msgs = git("log", "--all", "--format=%H %an <%ae> | %s")
for l in msgs.splitlines():
    for name, rx in SECRET.items():
        if rx.search(l):
            hits.append((name + " (commit message)", l[:8], "", "(see git log)"))

print("\n=== SECRET-LIKE FINDINGS (must be zero, or each one explained) ===")
if not hits:
    print("none")
for h in hits:
    print(" | ".join(h))
print("\n=== AUTHORS IN HISTORY (these become public) ===")
print("\n".join(sorted(set(git("log", "--all", "--format=%an <%ae>").splitlines()))))
print("\n=== ITEMS TO REVIEW BY EYE (identifiers, not necessarily secrets) ===")
for name, d in review.items():
    print(f"-- {name}: {len(d)} distinct")
    for val, ps in sorted(d.items())[:25]:
        if name == "email address":
            loc, _, dom = val.rpartition("@")
            shown = loc[:2] + "***@" + dom
        elif name == "ip address":
            shown = val
        else:
            shown = redact(val)
        print(f"   {shown}   in {len(ps)} file(s), e.g. {sorted(ps)[0]}")
sys.exit(1 if hits else 0)
