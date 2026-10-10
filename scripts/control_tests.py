"""Show, with real attempts, what the agent's database role can and cannot do.

Connects exactly as the agents do (the fia_agent role) and tries a fixed list of statements. Every
attempt runs inside a transaction that is rolled back, and every destructive attempt also has
`where false`, so nothing can change even if a control were broken. It writes results/control_tests.md
and exits 1 if any attempt did not behave as expected.

    python scripts/control_tests.py            (needs the database and the fia_agent password)
"""
import datetime
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fia_tools.db import agent_connection  # noqa: E402

DENIED = "42501"        # insufficient_privilege
CHECK = "23514"         # check_violation
ALLOWED = "allowed"


def new_finding(run_id, status=None):
    """An insert of one complete finding. The status column may only ever hold 'proposed'."""
    cols = "run_id, agent, risk, title, population, test_procedure, criteria, finding_condition, recommendation, evidence"
    vals = f"'{run_id}', 'ap_guardian', 'low', 'control test', 'p', 't', 'c', 'x', 'r', '[{{\"k\": 1}}]'::jsonb"
    if status:
        cols += ", status"
        vals += f", '{status}'"
    return f"insert into fia.findings ({cols}) values ({vals})"


# (what is attempted, statement, expected outcome)
CASES = [
    ("Read invoices (should work)", "select count(*) from fia.invoices", ALLOWED),
    ("Insert a proposed finding (should work)", new_finding("control-test"), ALLOWED),
    ("Insert a finding already marked 'accepted'", new_finding("control-test", "accepted"), CHECK),
    ("Update an invoice amount", "update fia.invoices set total_amt = total_amt where false", DENIED),
    ("Delete an invoice", "delete from fia.invoices where false", DENIED),
    ("Update a payment", "update fia.payments set amount = amount where false", DENIED),
    ("Delete a payment", "delete from fia.payments where false", DENIED),
    ("Change a vendor's active flag", "update fia.vendors set active = active where false", DENIED),
    ("Update a journal entry", "update fia.journal_entries set description = description where false", DENIED),
    ("Edit one of its own findings", "update fia.findings set risk = risk where false", DENIED),
    ("Delete one of its own findings", "delete from fia.findings where false", DENIED),
    ("Read the answer key", "select count(*) from fia_gt.manifest", DENIED),
    ("Write to the answer key", "delete from fia_gt.manifest where false", DENIED),
    ("Read the human review decisions", "select count(*) from fia.finding_reviews", DENIED),
    ("Create a table", "create table fia.control_test_x (a int)", DENIED),
]


class _Rollback(Exception):
    pass


def attempt(conn, sql):
    """Run one statement inside a transaction that is always rolled back. Returns (outcome, message)."""
    try:
        with conn.transaction():
            cur = conn.execute(sql)
            if cur.description:
                cur.fetchall()
            raise _Rollback()
    except _Rollback:
        return ALLOWED, "statement was accepted (then rolled back)"
    except psycopg.Error as e:
        return e.sqlstate or "error", str(e).strip().splitlines()[0]


def main():
    conn = agent_connection()
    who = conn.execute("select current_user").fetchone()[0]
    rows, bad = [], 0
    for label, sql, expected in CASES:
        outcome, message = attempt(conn, sql)
        ok = outcome == expected
        bad += not ok
        rows.append((label, sql, expected, outcome, message, ok))
    conn.close()

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = ["# Database permission check", "",
           f"Run {now} as database role `{who}`, the role both agents use.",
           "Every attempt ran in a transaction that was rolled back. Destructive attempts also used `where false`.",
           "This is a software control test: it shows the database enforces the limits, with no model involved.", "",
           "| Attempt | Expected | Result | Database message | Matches |", "| --- | --- | --- | --- | --- |"]
    for label, sql, expected, outcome, message, ok in rows:
        exp = "accepted" if expected == ALLOWED else {DENIED: "rejected (permission)", CHECK: "rejected (rule)"}[expected]
        res = "accepted" if outcome == ALLOWED else f"rejected ({outcome})"
        out.append(f"| {label} | {exp} | {res} | {message} | {'yes' if ok else 'NO'} |")
    out += ["", f"{len(rows) - bad} of {len(rows)} attempts behaved as expected."]
    path = ROOT / "results" / "control_tests.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"\nSaved to {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
