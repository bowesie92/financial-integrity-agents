"""Apply a generated bundle safely: check it, write the files, run the tests, undo everything if they fail.

Usage (from the repo root, with the venv active):
    python scripts/apply_bundle.py bundle26.txt --sha 0123456789ab [--lines 407] [--message "text"]

What it does, in order:
  1. Checks the bundle's check code (first 12 characters of its SHA-256). A mismatch changes nothing.
  2. Reads the file list and refuses any path outside the repo, any .git path and any .env file.
  3. Lists each file as new or changed, with lines added and removed.
  4. Writes the files, runs the tests, and puts every file back exactly as it was if the tests fail.
  5. On success prints git diff --stat and the git commands to run. It never commits.

Exit codes: 0 applied, tests passed. 2 bad check code or bad bundle (nothing changed).
3 tests failed (everything restored). 4 unsafe path (nothing changed).
"""
import argparse
import difflib
import hashlib
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HEADER = re.compile(r"^#=== FILE: (.+?) ===\n", re.M)
OK, BAD_BUNDLE, TESTS_FAILED, UNSAFE = 0, 2, 3, 4


class BundleError(Exception):
    def __init__(self, message, code=BAD_BUNDLE):
        super().__init__(message)
        self.code = code


def check_code(raw):
    return hashlib.sha256(raw).hexdigest()[:12]


def parse_bundle(text):
    """Return [(relative path, file text)] in bundle order. Same split rule as the old heredoc."""
    parts = HEADER.split(text)
    if len(parts) < 3 or parts[0] != "":
        raise BundleError("This does not look like a bundle: no '#=== FILE: path ===' lines at the start.")
    files = [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]
    names = [name for name, _ in files]
    if len(set(names)) != len(names):
        raise BundleError("The bundle lists the same file twice.")
    return files


def check_paths(files, repo):
    root = repo.resolve()
    for rel, _ in files:
        p = Path(rel)
        bad = None
        if p.is_absolute() or ".." in p.parts:
            bad = "points outside the repo"
        elif any(part == ".git" for part in p.parts):
            bad = "is inside .git"
        elif any(part.startswith(".env") or part.endswith(".env") for part in p.parts):
            bad = "is a secrets (.env) file"
        elif root not in (root / p).resolve().parents:
            bad = "points outside the repo"
        if bad:
            raise BundleError(f"Refused: {rel} {bad}. Nothing was changed.", UNSAFE)


def line_change(old, new):
    if old is None:
        return None
    a, b = old.decode("utf-8", "replace").splitlines(), new.splitlines()
    added = removed = 0
    for d in difflib.ndiff(a, b):
        if d.startswith("+ "):
            added += 1
        elif d.startswith("- "):
            removed += 1
    return added, removed


def restore(originals, created_dirs, repo):
    for rel, old in originals.items():
        target = repo / rel
        if old is None:
            if target.exists():
                target.unlink()
        else:
            target.write_bytes(old)
    for d in sorted(created_dirs, key=lambda x: len(x.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass


def apply_bundle(bundle, sha, repo=".", test_cmd="python -m pytest -q", no_tests=False, lines=None,
                 message=None, out=print):
    repo = Path(repo)
    bundle = Path(bundle)
    try:
        raw = bundle.read_bytes()
    except OSError as e:
        out(f"Cannot read {bundle}: {e}")
        return BAD_BUNDLE
    got = check_code(raw)
    want = (sha or "").strip().lower()
    if len(want) < 8 or not got.startswith(want):
        out(f"STOP: check code is {got} but you gave {want or 'nothing'}. The bundle was not saved correctly. "
            "Nothing was changed.")
        return BAD_BUNDLE
    n_lines = raw.count(b"\n")
    if lines is not None and n_lines != lines:
        out(f"STOP: the bundle has {n_lines} lines but you gave {lines}. Nothing was changed.")
        return BAD_BUNDLE
    out(f"Check code {got} and {n_lines} lines are correct.")
    try:
        files = parse_bundle(raw.decode("utf-8"))
        check_paths(files, repo)
    except BundleError as e:
        out(f"STOP: {e}")
        return e.code
    except UnicodeDecodeError:
        out("STOP: the bundle is not valid text. Nothing was changed.")
        return BAD_BUNDLE

    originals = {}
    out(f"This bundle will write {len(files)} file(s):")
    for rel, text in files:
        target = repo / rel
        originals[rel] = target.read_bytes() if target.exists() else None
        change = line_change(originals[rel], text)
        if change is None:
            out(f"  NEW      {rel}  ({len(text.splitlines())} lines)")
        elif originals[rel] == text.encode("utf-8"):
            out(f"  SAME     {rel}  (no change)")
        else:
            out(f"  CHANGED  {rel}  (+{change[0]} -{change[1]} lines)")

    created_dirs = []
    try:
        for rel, text in files:
            target = repo / rel
            missing = [p for p in reversed(target.parents) if not p.exists() and repo.resolve() in p.resolve().parents]
            target.parent.mkdir(parents=True, exist_ok=True)
            created_dirs.extend(missing)
            target.write_bytes(text.encode("utf-8"))
        out("Files written.")
        if no_tests:
            out("WARNING: tests were skipped (--no-tests). Run them yourself before committing.")
        else:
            out(f"Running the tests: {test_cmd}")
            result = subprocess.run(shlex.split(test_cmd), cwd=repo)
            if result.returncode != 0:
                restore(originals, created_dirs, repo)
                out("STOP: the tests failed, so every file was put back exactly as it was. Paste the failure to Claude.")
                return TESTS_FAILED
            out("Tests passed.")
    except BaseException:
        restore(originals, created_dirs, repo)
        out("STOP: interrupted or failed while applying, so every file was put back exactly as it was.")
        raise

    paths = [rel for rel, _ in files]
    if shutil.which("git") and (repo / ".git").exists():
        subprocess.run(["git", "diff", "--stat", "--"] + paths, cwd=repo)
        subprocess.run(["git", "status", "--short", "--"] + paths, cwd=repo)
    msg = message or f"Apply {bundle.name}"
    out("\nRead the diff, then commit with:")
    out("git add " + " ".join(shlex.quote(p) for p in paths))
    out("git commit -m " + shlex.quote(msg))
    return OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check, apply and test a bundle. Never commits.")
    ap.add_argument("bundle", help="path to the saved bundle, for example bundle26.txt")
    ap.add_argument("--sha", required=True, help="the check code shown on the bundles page (12 characters)")
    ap.add_argument("--lines", type=int, help="the line count shown on the bundles page")
    ap.add_argument("--repo", default=".", help="repo folder (default: current folder)")
    ap.add_argument("--message", help="commit message to print in the commit command")
    ap.add_argument("--test-cmd", default=f"{shlex.quote(sys.executable)} -m pytest -q",
                    help="test command (default: pytest -q with this Python)")
    ap.add_argument("--no-tests", action="store_true", help="skip the tests (docs-only bundles)")
    a = ap.parse_args(argv)
    return apply_bundle(a.bundle, a.sha, a.repo, a.test_cmd, a.no_tests, a.lines, a.message)


if __name__ == "__main__":
    sys.exit(main())
