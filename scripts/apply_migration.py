"""Apply one SQL migration file as fia_admin, in one transaction, then check the agent role.

Usage: python scripts/apply_migration.py db/002_use_tax.sql
Safe to re-run: the migration files use "if not exists".
"""
import argparse
from pathlib import Path

from setup_fia_roles import connect, load


def run(path, admin_connect, agent_connect):
    text = Path(path).read_text(encoding="utf-8")
    conn = admin_connect()
    conn.autocommit = False
    try:
        conn.execute(text)
        conn.commit()
    except Exception:
        conn.rollback()
        print("Migration failed and was rolled back. Nothing changed.")
        raise
    conn.autocommit = True
    cols = conn.execute("select column_name from information_schema.columns "
                        "where table_schema='fia' and table_name='invoices' "
                        "order by ordinal_position").fetchall()
    print("fia.invoices columns:", ", ".join(c[0] for c in cols))
    conn.close()
    agent = agent_connect()
    agent.execute("select tax_amt from fia.invoices limit 1")
    print("OK: agent role can read the new column")
    for stmt in ("alter table fia.invoices drop column tax_amt",):
        try:
            agent.execute(stmt)
            print("PROBLEM: agent role changed the schema")
        except Exception:
            print("OK: agent role cannot change the schema")
            break
    agent.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    args = ap.parse_args()
    env = load()
    run(args.file,
        lambda: connect(env, "fia_admin", env["SUPABASE_FIA_ADMIN_PASSWORD"]),
        lambda: connect(env, "fia_agent", env["SUPABASE_FIA_AGENT_PASSWORD"]))


if __name__ == "__main__":
    main()
