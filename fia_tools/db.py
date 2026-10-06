"""Database access for tools. Always the read-only agent role; every read runs in a read-only
transaction with a statement timeout, so a mistake in a tool cannot change data or hang."""
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

STATEMENT_TIMEOUT_MS = 5000


def agent_connection():
    """Connect as fia_agent. FIA_AGENT_DSN overrides (used by tests against a local copy)."""
    dsn = os.environ.get("FIA_AGENT_DSN")
    if dsn:
        return psycopg.connect(dsn, autocommit=True)
    scripts = str(Path(__file__).resolve().parent.parent / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from setup_fia_roles import connect, load  # the same helper the scripts use
    env = load()
    conn = connect(env, "fia_agent", env["SUPABASE_FIA_AGENT_PASSWORD"])
    conn.autocommit = True
    return conn


def query(conn, sql, params=None):
    """Run one read-only statement and return dict rows."""
    with conn.transaction():
        conn.execute("set transaction read only")
        conn.execute(f"set local statement_timeout = {STATEMENT_TIMEOUT_MS}")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
