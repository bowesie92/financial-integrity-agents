"""One-off setup (Phase 5, D32): the fia_notifier login and the finding_deliveries table. Safe to re-run.

Usage (from the repo root, venv active): python scripts/setup_notifier_role.py

What it does, in order:
  1. Makes a password for fia_notifier and appends it to the project secrets file (never printed).
  2. As the project's main role: creates or updates the fia_notifier login (no superuser, no create rights).
  3. As fia_admin: runs db/003_finding_deliveries.sql in one transaction (rolled back on failure).
  4. Checks what each login can and cannot do, and prints OK or PROBLEM for each line.
The notifier can read findings and read and write the delivery log. It cannot read invoices, journal entries,
human review decisions or the answer key, and it cannot change or delete a finding.
"""
import secrets
import sys
from pathlib import Path

import psycopg
from psycopg import sql

from setup_fia_roles import ENV, connect, load

ROLE, KEY = "fia_notifier", "SUPABASE_FIA_NOTIFIER_PASSWORD"
SQL_FILE = Path(__file__).resolve().parent.parent / "db" / "003_finding_deliveries.sql"

# (role, table, privilege, expected). One line of output each.
CHECKS = [
    (ROLE, "fia.findings", "SELECT", True),
    (ROLE, "fia.findings", "INSERT", False),
    (ROLE, "fia.findings", "UPDATE", False),
    (ROLE, "fia.findings", "DELETE", False),
    (ROLE, "fia.finding_deliveries", "SELECT", True),
    (ROLE, "fia.finding_deliveries", "INSERT", True),
    (ROLE, "fia.finding_deliveries", "UPDATE", False),
    (ROLE, "fia.finding_deliveries", "DELETE", False),
    (ROLE, "fia.invoices", "SELECT", False),
    (ROLE, "fia.journal_entries", "SELECT", False),
    (ROLE, "fia.finding_reviews", "SELECT", False),
    (ROLE, "fia_gt.manifest", "SELECT", False),
    ("fia_agent", "fia.finding_deliveries", "SELECT", False),
    ("fia_agent", "fia.finding_deliveries", "INSERT", False),
]


def check_privileges(conn):
    """Return [(ok, text)] for every line in CHECKS. conn needs .execute(sql, params).fetchone()."""
    out = []
    for role, table, priv, want in CHECKS:
        got = bool(conn.execute("select has_table_privilege(%s, %s, %s)", (role, table, priv)).fetchone()[0])
        verb = "can" if want else "cannot"
        out.append((got == want, f"{role} {verb} {priv.lower()} {table}"))
    return out


def main():
    env = load()
    if KEY not in env:
        env[KEY] = secrets.token_hex(24)
        with ENV.open("a") as f:
            f.write(f"{KEY}={env[KEY]}\n")
        print(f"A new password for {ROLE} was saved in the secrets file as {KEY}.")
    with connect(env, "postgres", env["SUPABASE_DB_PASSWORD"]) as conn:
        cur = conn.cursor()
        cur.execute("select 1 from pg_roles where rolname = %s", (ROLE,))
        verb = "alter" if cur.fetchone() else "create"
        cur.execute(sql.SQL(verb + " role {} login password {} nosuperuser nocreatedb nocreaterole noinherit "
                            "nobypassrls").format(sql.Identifier(ROLE), sql.Literal(env[KEY])))
        cur.execute(sql.SQL("alter role {} set statement_timeout = '30s'").format(sql.Identifier(ROLE)))
        cur.execute(sql.SQL("alter role {} set search_path = fia").format(sql.Identifier(ROLE)))
    print(f"login {ROLE} ready")

    admin = connect(env, "fia_admin", env["SUPABASE_FIA_ADMIN_PASSWORD"])
    admin.autocommit = False
    try:
        admin.execute(SQL_FILE.read_text(encoding="utf-8"))
        admin.commit()
    except Exception:
        admin.rollback()
        print("The migration failed and was rolled back. Nothing changed.")
        raise
    admin.autocommit = True
    print("OK: finding_deliveries table and grants applied")

    bad = 0
    for ok, text in check_privileges(admin):
        print(("OK:      " if ok else "PROBLEM: ") + text)
        bad += not ok
    admin.close()

    with connect(env, ROLE, env[KEY]) as conn:
        who = conn.execute("select current_user").fetchone()[0]
        n = conn.execute("select count(*) from fia.findings").fetchone()[0]
        print(f"OK:      {who} logs in and reads fia.findings ({n} rows)")
        try:
            conn.execute("select 1 from fia.invoices limit 1")
            print("PROBLEM: the notifier could read invoices")
            bad += 1
        except psycopg.errors.InsufficientPrivilege:
            print("OK:      the notifier cannot read invoices")
    print("\nFor the n8n Postgres credential (the password is in the secrets file under " + KEY + "):")
    print(f"  host {env['SUPABASE_POOLER_HOST']}   port 5432   database postgres   SSL require")
    print(f"  user {ROLE}.{env['SUPABASE_PROJECT_REF']}")
    if bad:
        print(f"\n{bad} PROBLEM line(s). Paste them and do not continue.")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
