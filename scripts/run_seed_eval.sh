#!/usr/bin/env bash
# Run the agents several times (dry runs, nothing is stored), score the new runs together,
# save the results, and print the commit command. It never commits and it never loads data.
#
# Usage, from the repo root with the venv active:
#   bash scripts/run_seed_eval.sh --seed 2 --runs 5 --tag seed2
#
# Options:
#   --seed N         the seed that is loaded in the database (required)
#   --runs N         runs per agent (default 5)
#   --tag NAME       names the result files: results/NAME_runs.txt, results/eval_NAME.txt and .json (required)
#   --agents "ap gl" which agents to run (default both)
#   --model NAME     model profile (default demo-plus, which is Sonnet 5.5)
#   --task-file F    give every run this task text (used for the targeted red-team run)
#   --allow-dirty    run even though tracked files have changed since the last commit
#   --yes            do not ask for confirmation
#
# This is a paid step: each run costs about $0.40 to $0.90 and is capped at $1.50.
# Exit codes: 0 done. 1 you declined. 2 bad options or wrong folder. 3 tracked files changed. 4 no runs found.

set -uo pipefail

PY="${PY:-python}"
SEED=""; RUNS=5; TAG=""; AGENTS="ap gl"; MODEL="demo-plus"; TASK_FILE=""; ALLOW_DIRTY=0; YES=0

die() { echo "STOP: $*" >&2; exit "${2:-2}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --seed) SEED="${2:-}"; shift 2 ;;
    --runs) RUNS="${2:-}"; shift 2 ;;
    --tag) TAG="${2:-}"; shift 2 ;;
    --agents) AGENTS="${2:-}"; shift 2 ;;
    --model) MODEL="${2:-}"; shift 2 ;;
    --task-file) TASK_FILE="${2:-}"; shift 2 ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --yes) YES=1; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
done

[[ "$SEED" =~ ^[0-9]+$ ]] || die "--seed needs a number"
[[ "$RUNS" =~ ^[0-9]+$ ]] && [ "$RUNS" -ge 1 ] && [ "$RUNS" -le 20 ] || die "--runs needs a number from 1 to 20"
[[ "$TAG" =~ ^[A-Za-z0-9_-]+$ ]] || die "--tag needs letters, digits, _ or - (for example seed2)"
for a in $AGENTS; do [ "$a" = ap ] || [ "$a" = gl ] || die "--agents can only contain ap and gl"; done
[ -f scripts/run_review.py ] && [ -f scripts/evaluate.py ] || die "run this from the repo root (scripts/run_review.py not found)"
[ -z "$TASK_FILE" ] || [ -f "$TASK_FILE" ] || die "task file $TASK_FILE not found"
git rev-parse --git-dir >/dev/null 2>&1 || die "this folder is not a git repo"

if ! git diff --quiet HEAD 2>/dev/null; then
  if [ "$ALLOW_DIRTY" -eq 0 ]; then
    echo "Tracked files have changed since the last commit:" >&2
    git status --short >&2
    die "commit or undo them first so the runs match a recorded version (or pass --allow-dirty)" 3
  fi
  echo "WARNING: running with uncommitted changes (--allow-dirty)."
fi

N_AGENTS=$(echo $AGENTS | wc -w)
TOTAL=$((RUNS * N_AGENTS))
EST=$(awk -v n="$TOTAL" 'BEGIN{printf "%.2f", n*0.70}')
WORST=$(awk -v n="$TOTAL" 'BEGIN{printf "%.2f", n*1.50}')

echo "Version:  $(git describe --tags --always 2>/dev/null) ($(git log -1 --oneline))"
echo "Plan:     $RUNS run(s) of: $AGENTS on model $MODEL, seed $SEED, tag $TAG ($TOTAL runs)"
[ -z "$TASK_FILE" ] || echo "Task:     $TASK_FILE"
echo "Cost:     about \$$EST (each run is capped at \$1.50, so the worst case is \$$WORST)"
echo "Check:    the database must hold seed $SEED (scripts/load_data.py --seed $SEED), and the Anthropic"
echo "          balance and the workspace monthly limit must cover the worst case."
if [ "$YES" -eq 0 ]; then
  read -r -p "Type yes to start: " ANS
  [ "$ANS" = "yes" ] || { echo "Not started."; exit 1; }
fi

mkdir -p runs results
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ls runs/*.jsonl 2>/dev/null | sort > "$TMP/before" || true

{
  for i in $(seq 1 "$RUNS"); do
    for a in $AGENTS; do
      args=(--agent "$a" --dry-run --model "$MODEL")
      [ -z "$TASK_FILE" ] || args+=(--task-file "$TASK_FILE")
      "$PY" scripts/run_review.py "${args[@]}"
      rc=$?
      [ "$rc" -eq 0 ] || echo "NOTE: run exited with code $rc. It is kept and counted."
    done
  done
} 2>&1 | tee "results/${TAG}_runs.txt"

ls runs/*.jsonl 2>/dev/null | sort > "$TMP/after" || true
NEW=$(comm -13 "$TMP/before" "$TMP/after")
COUNT=$(echo "$NEW" | grep -c . || true)
[ "$COUNT" -ge 1 ] || die "no new run logs were found, nothing to score" 4
[ "$COUNT" -eq "$TOTAL" ] || echo "WARNING: expected $TOTAL new run logs but found $COUNT. Check the output above."

echo
echo "Scoring $COUNT run(s) together on seed $SEED..."
# shellcheck disable=SC2086
"$PY" scripts/evaluate.py --runs $NEW --seed "$SEED" --json-out "results/eval_${TAG}.json" 2>&1 | tee "results/eval_${TAG}.txt"

echo
echo "Done. Read results/eval_${TAG}.txt, then commit with:"
echo "git add results/eval_${TAG}.json results/eval_${TAG}.txt results/${TAG}_runs.txt"
echo "git commit -m \"Evaluation $TAG: $RUNS run(s) of $AGENTS on seed $SEED\""
