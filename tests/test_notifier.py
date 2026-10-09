"""The delivery log migration and the notifier login checks. No database, no network."""
import re
import sys
from pathlib import Path

import pytest

root = Path(__file__).resolve().parent.parent
scripts = str(root / "scripts")
if scripts not in sys.path:
    sys.path.insert(0, scripts)

SQL = (root / "db" / "003_finding_deliveries.sql").read_text(encoding="utf-8").lower()


def statements():
    body = "\n".join(l for l in SQL.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip()]


def test_table_blocks_duplicates_and_points_at_findings():
    assert "primary key (finding_id, channel)" in SQL
    assert "references fia.findings (finding_id)" in SQL
    assert "channel in ('discord', 'email')" in SQL


def test_grants_are_the_least_the_notifier_needs():
    grants = [s for s in statements() if s.startswith("grant")]
    assert sorted(grants) == sorted([
        "grant usage on schema fia to fia_notifier",
        "grant select on fia.findings to fia_notifier",
        "grant select, insert on fia.finding_deliveries to fia_notifier"])
    assert "revoke all on fia.finding_deliveries from public" in statements()
    assert not re.search(r"\bto\s+(public|fia_agent)\b", SQL)


def test_migration_is_additive_and_has_an_undo_line():
    assert "drop table fia.finding_deliveries" in SQL
    for s in statements():
        assert not s.startswith(("drop", "alter", "truncate", "delete", "update")), s


class FakeConn:
    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def execute(self, text, params):
        self.asked.append(params)
        self._row = (self.answers[params],)
        return self

    def fetchone(self):
        return self._row


def test_privilege_checks_pass_when_every_answer_is_as_expected():
    import setup_notifier_role as s
    conn = FakeConn({(r, t, p): want for r, t, p, want in s.CHECKS})
    result = s.check_privileges(conn)
    assert len(result) == len(s.CHECKS) and all(ok for ok, _ in result)


def test_privilege_checks_report_a_wrong_grant():
    import setup_notifier_role as s
    answers = {(r, t, p): want for r, t, p, want in s.CHECKS}
    answers[("fia_notifier", "fia.invoices", "SELECT")] = True
    result = s.check_privileges(FakeConn(answers))
    bad = [text for ok, text in result if not ok]
    assert bad == ["fia_notifier cannot select fia.invoices"]


def test_checks_cover_the_dangerous_cases():
    import setup_notifier_role as s
    wanted = {(r, t, p) for r, t, p, want in s.CHECKS if not want}
    for case in [("fia_notifier", "fia.findings", "UPDATE"), ("fia_notifier", "fia.findings", "DELETE"),
                 ("fia_notifier", "fia.finding_reviews", "SELECT"), ("fia_notifier", "fia_gt.manifest", "SELECT"),
                 ("fia_agent", "fia.finding_deliveries", "INSERT")]:
        assert case in wanted
