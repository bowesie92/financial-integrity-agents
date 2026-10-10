"""One-off setup: schema fia and roles fia_admin, fia_agent. Safe to re-run."""
import os
import secrets
from pathlib import Path

import psycopg
from psycopg import sql

ENV = Path(os.environ.get("FIA_SECRETS_DIR", "/etc/financial-integrity-agents-secrets")) / "supabase.env"
ROLES = {"fia_admin": "SUPABASE_FIA_ADMIN_PASSWORD", "fia_agent": "SUPABASE_FIA_AGENT_PASSWORD"}


def load():
    out = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def connect(env, role, password):
    return psycopg.connect(
        host=env["SUPABASE_POOLER_HOST"], port=5432, dbname="postgres",
        user=f"{role}.{env['SUPABASE_PROJECT_REF']}", password=password,
        sslmode="require", connect_timeout=15, autocommit=True,
    )


def main():
    env = load()
    with ENV.open("a") as f:
        for key in ROLES.values():
            if key not in env:
                env[key] = secrets.token_hex(24)
                f.write(f"{key}={env[key]}\n")
    with connect(env, "postgres", env["SUPABASE_DB_PASSWORD"]) as conn:
        cur = conn.cursor()
        for role, key in ROLES.items():
            cur.execute("select 1 from pg_roles where rolname = %s", (role,))
            verb = "alter" if cur.fetchone() else "create"
            cur.execute(sql.SQL(verb + " role {} login password {} nosuperuser nocreatedb nocreaterole noinherit nobypassrls").format(sql.Identifier(role), sql.Literal(env[key])))
        cur.execute("grant fia_admin to postgres")
        cur.execute("create schema if not exists fia authorization fia_admin")
        cur.execute("grant usage on schema fia to fia_agent")
        cur.execute("alter role fia_agent set statement_timeout = '30s'")
        cur.execute("alter role fia_agent set search_path = fia")
    print("roles and schema ready")
    with connect(env, "fia_admin", env["SUPABASE_FIA_ADMIN_PASSWORD"]) as conn:
        conn.execute("create table fia._probe (id int)")
        conn.execute("drop table fia._probe")
    print("OK: fia_admin can log in and create tables in fia")
    with connect(env, "fia_agent", env["SUPABASE_FIA_AGENT_PASSWORD"]) as conn:
        print("OK: fia_agent logs in as", conn.execute("select current_user").fetchone()[0])
        try:
            conn.execute("create table fia._nope (id int)")
            print("PROBLEM: fia_agent could create a table")
        except psycopg.errors.InsufficientPrivilege:
            print("OK: fia_agent cannot create tables")


if __name__ == "__main__":
    main()
