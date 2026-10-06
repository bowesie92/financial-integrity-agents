"""Shared tools against the loaded seed 1 data, as the read-only agent role."""
import json

import psycopg
import pytest

from fia_tools.framework import ToolContext
from fia_tools.registry import build_registry

R = "Testing the shared tools against seed 1."
REG = build_registry("gl_sentinel")


def run(ctx, name, **args):
    return REG.run(ctx, name, {"reason": R, **args})


def test_describe_data(ctx):
    env = run(ctx, "describe_data")
    assert env["ok"], env
    r = env["result"]
    assert r["row_counts"]["journal_entries"] == 14975 and r["row_counts"]["invoices"] == 1750
    assert len(r["periods"]) == 13 and len(r["sites"]) == 3
    assert r["approval_limits"] == {"controller_from": 5000, "cfo_from": 25000}
    assert r["business_hours"]["start_hour_local_inclusive"] == 7
    assert len(json.dumps(env)) < 6000 and not env["truncated"]


def test_get_records_journal_entry_with_lines(ctx):
    env = run(ctx, "get_records", table="journal_entries", ids=["JE-2025-000001"])
    assert env["ok"], env
    rec = env["result"]["rows"][0]
    assert rec["je_id"] == "JE-2025-000001" and "untrusted_description" in rec and "description" not in rec
    assert rec["lines"] and set(rec["lines"][0]) >= {"account_id", "debit", "credit", "untrusted_memo"}
    total_d = sum(l["debit"] for l in rec["lines"])
    total_c = sum(l["credit"] for l in rec["lines"])
    assert round(total_d - total_c, 2) == 0


def test_get_records_other_tables_and_untrusted_labels(ctx):
    inv = run(ctx, "get_records", table="invoices", ids=["AP-000001"])["result"]["rows"][0]
    assert "untrusted_memo" in inv and "tax_amt" in inv and inv["lines"]
    ven = run(ctx, "get_records", table="vendors", ids=["V0001"])["result"]["rows"][0]
    assert "untrusted_name" in ven and "name" not in ven
    assert run(ctx, "get_records", table="gl_lines", ids=["1", "2"])["row_count"] == 2
    assert run(ctx, "get_records", table="users", ids=["u01"])["ok"]


def test_get_records_errors(ctx):
    assert run(ctx, "get_records", table="journal_entries", ids=["NOPE"])["error"]["code"] == "not_found"
    assert run(ctx, "get_records", table="gl_lines", ids=["abc"])["error"]["code"] == "invalid_input"
    assert run(ctx, "get_records", table="fia_gt.manifest", ids=["1"])["error"]["code"] == "invalid_input"
    assert run(ctx, "get_records", table="invoices", ids=[str(i) for i in range(26)])["error"]["code"] == "invalid_input"
    partial = run(ctx, "get_records", table="vendors", ids=["V0001", "V9999"])
    assert partial["ok"] and partial["result"]["not_found"] == ["V9999"]


def test_get_records_cannot_inject(ctx):
    env = run(ctx, "get_records", table="vendors", ids=["V0001'; drop table fia.vendors; --"])
    assert env["error"]["code"] == "not_found"
    assert run(ctx, "describe_data")["result"]["row_counts"]["vendors"] == 120


FINDING = dict(risk="low", title="Test finding one", population="All test records in seed 1.",
               test_procedure="Ran describe_data and get_records.", criteria="Records should exist.",
               finding_condition="Condition text with numbers 1 and 2.", cause="Not determinable from the data",
               effect="Not determinable from the data", recommendation="Review the cited records.",
               evidence=[{"table": "vendors", "id": "V0001", "note": "first vendor"}])


def test_propose_finding_dry_run_rolls_back(ctx):
    env = run(ctx, "propose_finding", **FINDING)
    assert env["ok"], env
    assert env["result"]["status"] == "proposed" and env["result"]["dry_run"] is True
    n = ctx.conn.execute("select count(*) from fia.findings where run_id = 'test-run'").fetchone()[0]
    assert n == 0


def test_propose_finding_rejects_missing_evidence_by_name(ctx):
    bad = {**FINDING, "evidence": [{"table": "vendors", "id": "V0001"}, {"table": "invoices", "id": "AP-999999"}]}
    env = run(ctx, "propose_finding", **bad)
    assert env["error"]["code"] == "not_found" and "invoices AP-999999" in env["error"]["message"] and "item 1" in env["error"]["message"]


@pytest.mark.parametrize("evidence,frag", [
    ([], "1 to 20"), ([{"table": "vendors"}], "exactly table, id"),
    ([{"table": "vendors", "id": "V0001"}] * 2, "repeats"), ([{"table": "accounts", "id": "6300"}], "one of"),
])
def test_propose_finding_validates_evidence(ctx, evidence, frag):
    env = run(ctx, "propose_finding", **{**FINDING, "evidence": evidence})
    assert env["ok"] is False and frag in env["error"]["message"]


def test_propose_finding_missing_fields_and_bad_risk(ctx):
    f = dict(FINDING); del f["cause"]
    assert run(ctx, "propose_finding", **f)["error"]["code"] == "invalid_input"
    assert run(ctx, "propose_finding", **{**FINDING, "risk": "critical"})["error"]["code"] == "invalid_input"


def test_duplicate_title_in_a_run_is_rejected(agent_conn):
    """Needs a real insert, so it uses a transaction the test rolls back itself."""
    ctx = ToolContext(conn=agent_conn, run_id="dup-run", agent="gl_sentinel", dry_run=False)
    with agent_conn.transaction():  # outer transaction; the tool's own becomes a savepoint
        first = REG.run(ctx, "propose_finding", {"reason": R, **FINDING})
        second = REG.run(ctx, "propose_finding", {"reason": R, **FINDING})
        assert first["ok"] and second["error"]["code"] == "invalid_input"
        raise psycopg.Rollback()
    assert agent_conn.execute("select count(*) from fia.findings where run_id = 'dup-run'").fetchone()[0] == 0


def test_finish_review(ctx):
    env = run(ctx, "finish_review", summary="Reviewed the data and found nothing to add.", checked=["Benford on Q3"])
    assert env["ok"] and ctx.finished and ctx.finish["not_checked"] == []
    assert run(ctx, "finish_review", summary="short", checked=["x"])["error"]["code"] == "invalid_input"


def test_get_regulation(ctx):
    env = run(ctx, "get_regulation", state="AZ", topic="use_tax_out_of_state_purchase")
    assert env["ok"] and env["result"]["rows"][0]["source_url"].startswith("https://")
    assert run(ctx, "get_regulation", state="NY", topic="use_tax_rate")["error"]["code"] == "invalid_input"


def test_agent_role_really_is_read_only(agent_conn):
    for stmt in ("update fia.vendors set name = 'x'", "delete from fia.invoices",
                 "insert into fia.sites values (99,'x','AZ','America/Phoenix')",
                 "select 1 from fia_gt.manifest", "select 1 from fia.finding_reviews"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            agent_conn.execute(stmt)


# ---- wording guards (memo rules enforced where the text is written) ---------------------------
def test_wording_patterns():
    from fia_tools.shared import ACTION_WORDS, FRAUD_CONCLUSION
    for bad in ("Require the poster to reverse and repost the entries", "Void the entries", "Delete the duplicates",
                "Consider posting a correcting entry"):
        assert ACTION_WORDS.search(bad), bad
    for ok in ("Obtain support and review the approval", "Ask the poster why the entries were posted after close"):
        assert not ACTION_WORDS.search(ok), ok
    for bad in ("No fraud indicators were detected", "There is no evidence of fraud"):
        assert FRAUD_CONCLUSION.search(bad), bad
    assert not FRAUD_CONCLUSION.search("This does not conclude that fraud occurred.")


def test_propose_finding_rejects_action_advice_and_fraud_conclusions(ctx):
    e = run(ctx, "propose_finding", **{**FINDING, "recommendation": "Have the poster reverse and repost the entries."})
    assert e["error"]["code"] == "invalid_input" and "investigative only" in e["error"]["message"]
    e = run(ctx, "propose_finding", **{**FINDING, "effect": "No fraud indicators were found in this population."})
    assert e["error"]["code"] == "invalid_input" and "fraud" in e["error"]["message"]
    assert run(ctx, "propose_finding", **FINDING)["ok"] is True


def test_finish_review_rejects_a_fraud_conclusion(ctx):
    base = {"summary": "Reviewed the ledger. No fraud indicators were detected.", "checked": ["digit tests"]}
    assert run(ctx, "finish_review", **base)["error"]["code"] == "invalid_input"
