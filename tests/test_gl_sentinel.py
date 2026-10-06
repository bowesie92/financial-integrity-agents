"""GL Sentinel tests: the prompt, the memo writer, the transcript, and one run with a scripted model
against the real tools and test database. No network and no model cost."""
import json
from decimal import Decimal

import pytest

from fia_agents.gl_sentinel import AGENT, DEFAULT_TASK, build_system_prompt, new_run_id, run_review
from fia_agents.kill import KillSwitch
from fia_agents.limits import Limits
from fia_agents.loop import RunResult
from fia_agents.memo import findings_for_run, findings_from_events, findings_from_log, render_document, render_memo
from fia_agents.runlog import RunLog
from fia_agents.transcript import render_transcript
from fia_llm.fake import FakeClient, multi_tool_turn, tool_turn

R = "Checking this for the GL Sentinel test run."
FINDING = {"risk": "medium", "title": "Possible after-hours posting pattern by one user",
           "population": "fia.journal_entries, 2025, entries by user u06 in the test database",
           "test_procedure": "timing_scan with rule after_hours grouped by user",
           "criteria": "Entries are expected inside business hours for the poster's site.",
           "finding_condition": "The tool listed entries outside 07:00 to 19:00 local time for this user.",
           "cause": "Possible deadline pressure; consistent with routine close work.",
           "effect": "Not determinable from the data",
           "recommendation": "Ask the poster for support and review the approvals on these entries.",
           "evidence": [{"table": "users", "id": "u06", "note": "poster under test"}]}


# ---- the prompt -------------------------------------------------------------------------------
def test_prompt_states_the_call_limit_and_when_to_wrap_up():
    p = build_system_prompt(Limits(max_calls=40))
    assert "at most 40 model calls" in p and "about 32 calls" in p
    assert "{MAX_CALLS}" not in p and "{WRAP_UP_AT}" not in p
    assert "at most 12 model calls" in build_system_prompt(Limits(max_calls=12))


def test_prompt_carries_the_memo_rules_and_rubric():
    p = build_system_prompt()
    for need in ("describe_data", "gl_population_profile", "finish_review", "$25,000", "$5,000",
                 "vendor-supplied text", "Do not conclude that fraud occurred", "Not determinable from the data",
                 "5,000 or more lines", "never recommend posting"):
        assert need.lower() in p.lower(), need


def test_prompt_does_not_leak_the_test_design():
    p = build_system_prompt().lower()
    for banned in ("planted", "decoy", "seed", "ground truth", "manifest", "baseline", "q3", "fresno", "controller"):
        assert banned not in p, banned


def test_run_ids_are_unique_and_labelled():
    a, b = new_run_id(), new_run_id()
    assert a != b and a.startswith("gl-")


# ---- memos ------------------------------------------------------------------------------------
def test_render_memo_has_every_template_section():
    m = render_memo({**FINDING, "evidence": [{"table": "invoices", "id": "INV-1"}, {"table": "invoices", "id": "INV-2"},
                                             {"table": "vendors", "id": "V0001", "note": "the vendor"}]}, 1)
    for label in ("Risk", "Population", "Procedure", "Criteria", "Condition", "Cause", "Effect", "Recommendation", "Evidence"):
        assert f"**{label}:**" in m, label
    assert m.startswith("### 1. Possible after-hours posting pattern")
    assert "invoices INV-1, INV-2; vendors V0001" in m and "- vendors V0001: the vendor" in m


def result(**kw):
    base = dict(run_id="gl-test", status="finished", detail="", calls=3, tool_calls=4, findings=1, input_tokens=1000,
                output_tokens=200, cost_usd=Decimal("0.0123"), wall_s=4.2,
                finish={"summary": "Reviewed timing; one item proposed.", "checked": ["timing_scan after_hours"],
                        "not_checked": ["Approvals outside the system"]})
    return RunResult(**{**base, **kw})


def test_document_lists_checked_and_not_checked_and_the_proposal_notice():
    d = render_document(result(), [FINDING], "dev", "database", "gl-1")
    assert "## Findings (1)" in d and "## Checked" in d and "## Not checked in this run" in d
    assert "Approvals outside the system" in d and "Nothing was posted, changed or paid" in d
    assert "INCOMPLETE" not in d and "Cost: $0.0123" in d


def test_document_flags_an_incomplete_run_and_unpriced_cost():
    d = render_document(result(status="max_calls", finish=None, cost_usd=None), [], "demo", "run log", "gl-1")
    assert "INCOMPLETE RUN" in d and "max_calls" in d and "No findings were proposed" in d and "not priced" in d
    assert "Nothing was listed by the model" in d


def test_findings_from_events_keeps_only_successful_proposals(tmp_path):
    p = tmp_path / "r.jsonl"
    log = RunLog(p, keep=True)
    log.event("tool_call", name="propose_finding", ok=False, args=FINDING)
    log.event("tool_call", name="get_records", ok=True, args={"table": "users"})
    log.event("tool_call", name="propose_finding", ok=True, args={**FINDING, "reason": R})
    log.close()
    got = findings_from_events(log.events)
    assert len(got) == 1 and got[0]["title"] == FINDING["title"] and "reason" not in got[0]
    assert findings_from_log(p)[0]["evidence"] == FINDING["evidence"]


def test_transcript_shows_reasons_and_results():
    log = RunLog(keep=True)
    log.event("run_start", run_id="gl-t", agent=AGENT, dry_run=True, git_commit="abc", provider="fake", alias="dev",
              model="claude-haiku-4-5-20251001", thinking=None, effort=None, limits={"max_calls": 40},
              system_sha256="0123456789abcdef", tools=["describe_data"])
    log.event("llm_call", call=1, stop_reason="tool_use", input_tokens=10, output_tokens=5, cost_usd=0.001,
              latency_s=0.5, text="Starting with orientation.", tool_use=["describe_data"])
    log.event("tool_call", call=1, name="describe_data", reason="Orientation first.", args={"reason": "Orientation first."},
              ok=True, row_count=3, truncated=False, result={"ok": True, "result": {"tables": 8}})
    log.event("run_end", status="finished", detail="", calls=1, tool_calls=1, findings=0, input_tokens=10,
              output_tokens=5, cost_usd=0.001, wall_s=0.5, finish=None)
    t = render_transcript(log.events)
    assert "Starting with orientation." in t and "WHY: Orientation first." in t and "END status finished" in t


# ---- a whole run with a scripted model, the real tools and the test database -------------------
def test_run_review_dry_run_end_to_end(agent_conn, tmp_path):
    script = [multi_tool_turn([
                  ("describe_data", {"reason": "Orientation first, as the prompt says."}, "d1"),
                  ("gl_population_profile", {"reason": "Check the population size before any digit test."}, "d2")]),
              tool_turn("propose_finding", {"reason": "One unexplained signal, proposing it.",
                                            **{k: v for k, v in FINDING.items() if k != "evidence"},
                                            "evidence": [{"table": "vendors", "id": "V0001", "note": "exists"}]},
                        call_id="p1"),
              tool_turn("finish_review", {"reason": "Everything I planned is covered.",
                                          "summary": "Scripted test review with one proposal.",
                                          "checked": ["population profile"], "not_checked": ["digit tests"]}, call_id="f1")]
    client = FakeClient(script)
    res, path = run_review(client, agent_conn, run_id="gl-test-dry", dry_run=True, log_dir=tmp_path,
                           kill=KillSwitch(path=tmp_path / "no_kill"))
    assert res.status == "finished" and res.findings == 1 and res.tool_calls == 4
    sent_system = client.calls[0]["system"]
    assert "at most 40 model calls" in sent_system
    events = [json.loads(x) for x in path.read_text().splitlines()]
    assert events[0]["event"] == "run_start" and events[-1]["event"] == "run_end"
    assert [e["name"] for e in events if e["event"] == "tool_call"][-2:] == ["propose_finding", "finish_review"]
    assert findings_for_run(agent_conn, "gl-test-dry") == []          # a dry run stores nothing
    assert len(findings_from_log(path)) == 1                           # but the log has it
    doc = render_document(res, findings_from_log(path), "dev", "run log", "gl-1")
    assert "digit tests" in doc and FINDING["title"] in doc


def test_real_run_findings_are_read_back_from_the_database(agent_conn):
    """A real (not dry) run stores the row; the memo is built from the stored row. Rolled back after."""
    import psycopg
    script = [tool_turn("propose_finding", {"reason": "One unexplained signal, proposing it.",
                                            **{k: v for k, v in FINDING.items() if k != "evidence"},
                                            "evidence": [{"table": "users", "id": "u06", "note": "poster under test"}]},
                        call_id="p1"),
              tool_turn("finish_review", {"reason": "Everything I planned is covered.",
                                          "summary": "Scripted test review with one proposal.",
                                          "checked": ["timing"]}, call_id="f1")]
    with agent_conn.transaction():
        res, _ = run_review(FakeClient(script), agent_conn, run_id="gl-test-real", dry_run=False, log_dir="/tmp/gl_test_logs",
                            kill=KillSwitch(path="/nonexistent/kill"))
        rows = findings_for_run(agent_conn, "gl-test-real")
        assert res.findings == 1 and len(rows) == 1
        assert rows[0]["title"] == FINDING["title"] and rows[0]["evidence"][0]["id"] == "u06"
        memo = render_memo(rows[0], 1)
        assert "**Risk:** medium" in memo and "users u06" in memo
        raise psycopg.Rollback()
    assert agent_conn.execute("select count(*) from fia.findings where run_id = 'gl-test-real'").fetchone()[0] == 0
