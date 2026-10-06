"""Shared fixtures. Tool tests need the read-only agent connection. They fail loudly when it is
missing; set FIA_SKIP_DB_TESTS=1 to skip them on purpose."""
import os

import pytest


@pytest.fixture(scope="session")
def agent_conn():
    if os.environ.get("FIA_SKIP_DB_TESTS") == "1":
        pytest.skip("FIA_SKIP_DB_TESTS=1")
    from fia_tools.db import agent_connection
    conn = agent_connection()
    yield conn
    conn.close()


@pytest.fixture()
def ctx(agent_conn):
    from fia_tools.framework import ToolContext
    return ToolContext(conn=agent_conn, run_id="test-run", agent="gl_sentinel", dry_run=True)
