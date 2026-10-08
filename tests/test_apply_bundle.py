"""scripts/apply_bundle.py: check code, safe paths, tests, and rollback. No database, no network."""
import hashlib
import sys
from pathlib import Path

import pytest

scripts = str(Path(__file__).resolve().parent.parent / "scripts")
if scripts not in sys.path:
    sys.path.insert(0, scripts)
import apply_bundle as ab  # noqa: E402

PASS = f"{sys.executable} -c pass"
FAIL = f"{sys.executable} -c \"import sys; sys.exit(1)\""


def make(tmp_path, files, name="bundle9.txt"):
    text = "".join(f"#=== FILE: {p} ===\n{t}" for p, t in files)
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path, hashlib.sha256(text.encode()).hexdigest()[:12], text.count("\n")


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    (r / "old.py").write_bytes(b"print('old')\nline2\n")
    return r


def run(bundle, sha, repo, **kw):
    out = []
    kw.setdefault("test_cmd", PASS)
    code = ab.apply_bundle(bundle, sha, repo, out=out.append, **kw)
    return code, "\n".join(out)


def test_applies_when_tests_pass_and_prints_the_commit_command(tmp_path, repo):
    b, sha, n = make(tmp_path, [("old.py", "print('new')\nline2\nline3\n"), ("pkg/sub/new.py", "x = 1\n")])
    code, out = run(b, sha, repo, lines=n)
    assert code == ab.OK
    assert (repo / "old.py").read_text() == "print('new')\nline2\nline3\n"
    assert (repo / "pkg/sub/new.py").read_text() == "x = 1\n"
    assert "CHANGED  old.py  (+2 -1 lines)" in out and "NEW      pkg/sub/new.py" in out
    assert "git add old.py pkg/sub/new.py" in out and "git commit -m" in out and "Apply bundle9.txt" in out
    assert "Tests passed." in out


def test_a_wrong_check_code_changes_nothing(tmp_path, repo):
    b, sha, _ = make(tmp_path, [("old.py", "changed\n"), ("new.py", "x\n")])
    code, out = run(b, "000000000000", repo)
    assert code == ab.BAD_BUNDLE and "STOP" in out
    assert (repo / "old.py").read_bytes() == b"print('old')\nline2\n" and not (repo / "new.py").exists()


def test_a_short_or_missing_check_code_is_refused(tmp_path, repo):
    b, sha, _ = make(tmp_path, [("new.py", "x\n")])
    assert run(b, "", repo)[0] == ab.BAD_BUNDLE
    assert run(b, sha[:4], repo)[0] == ab.BAD_BUNDLE
    assert not (repo / "new.py").exists()


def test_a_wrong_line_count_changes_nothing(tmp_path, repo):
    b, sha, n = make(tmp_path, [("new.py", "x\n")])
    code, out = run(b, sha, repo, lines=n + 1)
    assert code == ab.BAD_BUNDLE and "lines" in out and not (repo / "new.py").exists()


def test_failing_tests_put_every_file_back_exactly(tmp_path, repo):
    b, sha, _ = make(tmp_path, [("old.py", "broken\n"), ("deep/er/new.py", "x\n")])
    code, out = run(b, sha, repo, test_cmd=FAIL)
    assert code == ab.TESTS_FAILED and "put back" in out
    assert (repo / "old.py").read_bytes() == b"print('old')\nline2\n"
    assert not (repo / "deep").exists()


@pytest.mark.parametrize("path", ["../evil.py", "/etc/evil.py", "x/../../evil.py", ".git/config", "sub/.git/hooks/x",
                                  ".env", "secrets/anthropic.env", ".env.local"])
def test_unsafe_paths_are_refused_before_anything_is_written(tmp_path, repo, path):
    b, sha, _ = make(tmp_path, [("old.py", "changed\n"), (path, "bad\n")])
    code, out = run(b, sha, repo)
    assert code == ab.UNSAFE and "Refused" in out
    assert (repo / "old.py").read_bytes() == b"print('old')\nline2\n"
    assert not (tmp_path / "evil.py").exists()


def test_a_file_that_is_not_a_bundle_is_refused(tmp_path, repo):
    p = tmp_path / "junk.txt"
    p.write_bytes(b"hello\n")
    sha = hashlib.sha256(b"hello\n").hexdigest()[:12]
    code, out = run(p, sha, repo)
    assert code == ab.BAD_BUNDLE and "bundle" in out.lower()


def test_the_same_file_twice_is_refused(tmp_path, repo):
    b, sha, _ = make(tmp_path, [("a.py", "1\n"), ("a.py", "2\n")])
    assert run(b, sha, repo)[0] == ab.BAD_BUNDLE and not (repo / "a.py").exists()


def test_no_tests_flag_warns_and_still_applies(tmp_path, repo):
    b, sha, _ = make(tmp_path, [("docs/note.md", "hello\n")])
    code, out = run(b, sha, repo, no_tests=True, test_cmd=FAIL)
    assert code == ab.OK and "WARNING" in out and (repo / "docs/note.md").exists()


def test_message_option_goes_into_the_commit_command(tmp_path, repo):
    b, sha, _ = make(tmp_path, [("a.py", "1\n")])
    code, out = run(b, sha, repo, message="Add a thing")
    assert code == ab.OK and "git commit -m 'Add a thing'" in out


def test_the_script_never_runs_git_commit(tmp_path, repo):
    src = (Path(scripts) / "apply_bundle.py").read_text()
    assert '["git", "commit"' not in src and "'git', 'commit'" not in src


def test_main_reads_arguments(tmp_path, repo, capsys):
    b, sha, n = make(tmp_path, [("a.py", "1\n")])
    code = ab.main([str(b), "--sha", sha, "--lines", str(n), "--repo", str(repo), "--test-cmd", PASS])
    assert code == 0 and (repo / "a.py").exists()
