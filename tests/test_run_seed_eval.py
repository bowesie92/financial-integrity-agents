"""scripts/run_seed_eval.sh with stand-in run and evaluate scripts. No database, no network, no cost."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_seed_eval.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None, reason="needs bash and git")

RUN_REVIEW = '''import argparse, pathlib
ap = argparse.ArgumentParser()
ap.add_argument("--agent"); ap.add_argument("--model"); ap.add_argument("--task-file"); ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
runs = pathlib.Path("runs"); runs.mkdir(exist_ok=True)
n = len(list(runs.glob("*.jsonl"))) + 1
(runs / f"{a.agent}-{n:03d}.jsonl").write_text("{}\\n")
print("status finished", a.agent, a.model, a.task_file)
'''
EVALUATE = '''import argparse, json, pathlib
ap = argparse.ArgumentParser()
ap.add_argument("--runs", nargs="+"); ap.add_argument("--seed"); ap.add_argument("--json-out")
a = ap.parse_args()
pathlib.Path(a.json_out).write_text(json.dumps({"runs": a.runs, "seed": a.seed}))
print("SCORED", len(a.runs), "runs on seed", a.seed)
'''


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    (r / "scripts/run_review.py").write_text(RUN_REVIEW)
    (r / "scripts/evaluate.py").write_text(EVALUATE)
    (r / "tracked.txt").write_text("a\n")
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    git(r, "add", ".")
    git(r, "commit", "-q", "-m", "start")
    return r


def go(repo, *args, stdin=""):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=repo, input=stdin, text=True, capture_output=True,
                          env={"PATH": __import__("os").environ["PATH"], "PY": sys.executable, "HOME": str(repo)})


def test_runs_every_agent_scores_together_and_prints_the_commit_command(repo):
    r = go(repo, "--seed", "7", "--runs", "2", "--tag", "t1", "--yes")
    assert r.returncode == 0, r.stderr
    assert len(list((repo / "runs").glob("*.jsonl"))) == 4
    assert "SCORED 4 runs on seed 7" in (repo / "results/eval_t1.txt").read_text()
    assert (repo / "results/eval_t1.json").exists() and (repo / "results/t1_runs.txt").exists()
    assert "git add results/eval_t1.json results/eval_t1.txt results/t1_runs.txt" in r.stdout
    assert "git commit" in r.stdout and "Cost:" in r.stdout and "demo-plus" in r.stdout


def test_only_the_new_runs_are_scored(repo):
    (repo / "runs").mkdir()
    (repo / "runs/old-001.jsonl").write_text("{}\n")
    r = go(repo, "--seed", "3", "--runs", "1", "--agents", "ap", "--tag", "t2", "--yes")
    assert r.returncode == 0, r.stderr
    scored = (repo / "results/eval_t2.json").read_text()
    assert "old-001" not in scored and "ap-002" in scored
    assert "SCORED 1 runs" in (repo / "results/eval_t2.txt").read_text()


def test_task_file_and_model_are_passed_to_every_run(repo):
    (repo / "task.txt").write_text("review these\n")
    r = go(repo, "--seed", "2", "--runs", "1", "--agents", "ap", "--tag", "t3", "--model", "dev",
           "--task-file", "task.txt", "--yes")
    assert r.returncode == 0, r.stderr
    assert "ap dev task.txt" in (repo / "results/t3_runs.txt").read_text()


def test_declining_the_question_runs_nothing(repo):
    r = go(repo, "--seed", "7", "--runs", "1", "--tag", "t4", stdin="no\n")
    assert r.returncode == 1 and not (repo / "runs").exists()
    r = go(repo, "--seed", "7", "--runs", "1", "--tag", "t4", stdin="yes\n")
    assert r.returncode == 0 and len(list((repo / "runs").glob("*.jsonl"))) == 2


def test_changed_tracked_files_stop_the_run(repo):
    (repo / "tracked.txt").write_text("changed\n")
    r = go(repo, "--seed", "7", "--runs", "1", "--tag", "t5", "--yes")
    assert r.returncode == 3 and not (repo / "runs").exists() and "commit or undo" in r.stderr
    r = go(repo, "--seed", "7", "--runs", "1", "--tag", "t5", "--yes", "--allow-dirty")
    assert r.returncode == 0 and "WARNING" in r.stdout


def test_untracked_files_do_not_stop_the_run(repo):
    (repo / "scratch.txt").write_text("x\n")
    assert go(repo, "--seed", "7", "--runs", "1", "--tag", "t6", "--yes").returncode == 0


@pytest.mark.parametrize("args", [["--runs", "1", "--tag", "x"], ["--seed", "x", "--tag", "x"], ["--seed", "1"],
                                  ["--seed", "1", "--tag", "a b"], ["--seed", "1", "--tag", "x", "--runs", "0"],
                                  ["--seed", "1", "--tag", "x", "--agents", "zz"], ["--seed", "1", "--tag", "x", "--bogus"],
                                  ["--seed", "1", "--tag", "x", "--task-file", "missing.txt"]])
def test_bad_options_are_refused_without_running(repo, args):
    r = go(repo, *args, "--yes")
    assert r.returncode == 2 and "STOP" in r.stderr and not (repo / "runs").exists()


def test_a_failed_run_is_kept_and_counted(repo):
    (repo / "scripts/run_review.py").write_text(RUN_REVIEW + "\nimport sys\nsys.exit(1)\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "failing stand-in")
    r = go(repo, "--seed", "7", "--runs", "2", "--agents", "gl", "--tag", "t7", "--yes")
    assert r.returncode == 0 and "NOTE: run exited with code 1" in (repo / "results/t7_runs.txt").read_text()
    assert "SCORED 2 runs" in (repo / "results/eval_t7.txt").read_text()


def test_no_new_logs_stops_before_scoring(repo):
    (repo / "scripts/run_review.py").write_text("print('nothing written')\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "no logs")
    r = go(repo, "--seed", "7", "--runs", "1", "--tag", "t8", "--yes")
    assert r.returncode == 4 and not (repo / "results/eval_t8.json").exists()
