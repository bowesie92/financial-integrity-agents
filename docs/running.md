# Running it yourself

You need Python 3, a free [Supabase](https://supabase.com) project and an [Anthropic API key](https://console.anthropic.com). Review runs are paid: roughly $0.40 to $1.00 each on Sonnet 5.5, capped at $1.50 per review.

## 1. Install

```
git clone https://github.com/bowesie92/financial-integrity-agents.git
cd financial-integrity-agents
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Add your secrets

Create a folder outside the repository with two files, `anthropic.env` and `supabase.env`, and point `FIA_SECRETS_DIR` at it:

```
export FIA_SECRETS_DIR=/path/to/your/secrets-folder
```

If `FIA_SECRETS_DIR` is not set, the scripts use `/etc/financial-integrity-agents-secrets/`. [`deploy/secrets.env.example`](../deploy/secrets.env.example) lists every variable name. The folder lives outside the repository on purpose, so it can never be committed.

## 3. Create the database

```
python scripts/apply_schema.py
python scripts/apply_migration.py db/002_use_tax.sql
python scripts/apply_migration.py db/003_finding_deliveries.sql
python scripts/setup_fia_roles.py
python scripts/setup_notifier_role.py
```

These scripts run for real as soon as you start them.

## 4. Generate and load the synthetic company

```
python -m generator --seed 1
python scripts/load_data.py --seed 1
```

## 5. Check the code

```
pytest
```

The tests that need the loaded database (the tool tests and the permission tests) cannot run until step 4 is done. Without a database, run `FIA_SKIP_DB_TESTS=1 pytest` to skip them on purpose. This is what the GitHub Actions run does.

To see the permission limits enforced, run `python scripts/control_tests.py`. It saves its output to `results/control_tests.md`.

## 6. Run a review

`--dry-run` runs the review without storing any findings.

```
python scripts/run_review.py --agent ap --model demo-plus --dry-run
```

Use `--agent gl` for the ledger agent. Drop `--dry-run` to store the findings in the database. The alias `demo-plus` is the repository's name for Sonnet 5.5.

## 7. Measure it

This runs the agent several times against a seed and scores each run. It is paid.

```
bash scripts/run_seed_eval.sh --seed 3 --runs 5 --tag mytest
```

## 8. Rebuild the published tables (free)

```
python scripts/analysis/rebuild_tables.py
```

This reads the committed files in `results/` and prints the tables the case study uses. It needs no database and no API key.

Scheduling and delivery (systemd timers, n8n workflow) are explained in [`deploy/README.md`](../deploy/README.md).
