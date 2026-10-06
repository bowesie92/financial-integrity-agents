"""Loop tests. They use a scripted fake model and stub tools, so they cost nothing and need no database,
except the last one, which runs the real GL Sentinel tools against the test database."""
import json
from decimal import Decimal

import pytest

from fia_agents.kill import KillSwitch
from fia_agents.limits import Limits, RunState, check_limits
from fia_agents.loop import NUDGE, run_agent
from fia_agents.runlog import RunLog
from fia_llm.errors import FatalLLMError
from fia_llm.fake import FakeClient, multi_tool_turn, raw_turn, text_turn, tool_turn
from fia_tools.framework import Param, Registry, ToolContext, ToolSpec

R = "Checking this for the loop test run."
FIN = {"reason": R, "summary": "Reviewed everything that was asked.", "checked": ["x"]}


class Conn:
    closed = False


def _finish(ctx, args):
    ctx.finished = True
    ctx.finish = {"summary": args.get("summary", "done"), "checked": ["x"], "not_checked": []}
    return {"finished": True}


def _boom(ctx, args):
    raise RuntimeError("secret internals")


def _propose(ctx, args):
    return {"finding_id": "f1"}


def make(extra=()):
    tools = [ToolSpec("echo", "echo", {}, lambda c, a: {"rows": [1]}),
             ToolSpec("boom", "boom", {}, _boom),
             ToolSpec("propose_finding", "p", {}, _propose),
             ToolSpec("finish_review", "f", {"summary": Param("str", "s"), "checked": Param("str_list", "c")}, _finish), *extra]
    return Registry(tools)


def go(script, limits=None, kill=None, alias="dev", clock=None, ctx=None, registry=None):
    client = FakeClient(script, alias=alias)
    ctx = ctx or ToolContext(Conn(), "run-1", "gl_sentinel", dry_run=True)
    log = RunLog(keep=True)
    kw = {"clock": clock} if clock else {}
    res = run_agent(client, registry or make(), ctx, "system text", "Do the review.", limits=limits, log=log,
                    kill=kill or KillSwitch(path="/nonexistent/kill"), **kw)
    return res, client, log, ctx


def echo(i=1):
    return tool_turn("echo", {"reason": R}, call_id=f"t{i}")


def fin(i=99):
    return tool_turn("finish_review", FIN, call_id=f"t{i}")


# ---- normal runs -----------------------------------------------------------------------------
def test_happy_path():
    res, client, log, ctx = go([echo(1), echo(2), fin()])
    assert res.status == "finished" and res.finished and res.calls == 3 and res.tool_calls == 3
    assert res.finish["summary"].startswith("Reviewed")
    assert [e["event"] for e in log.events][0] == "run_start" and log.events[-1]["event"] == "run_end"


def test_parallel_tool_calls_answered_in_one_message_in_order():
    res, client, _, _ = go([multi_tool_turn([("echo", {"reason": R}, "a"), ("echo", {"reason": R}, "b")]), fin()])
    last = client.calls[1]["messages"][-1]
    assert last["role"] == "user" and [b["tool_use_id"] for b in last["content"]] == ["a", "b"]
    assert res.status == "finished"


def test_finish_in_same_turn_as_other_tools():
    res, client, _, ctx = go([multi_tool_turn([("echo", {"reason": R}, "a"), ("finish_review", FIN, "b")])])
    assert res.status == "finished" and res.calls == 1 and res.tool_calls == 2


def test_findings_counted_only_when_successful():
    ok = ("propose_finding", {"reason": R}, "a")
    bad = ("propose_finding", {"reason": "short"}, "b")
    res, _, _, _ = go([multi_tool_turn([ok, bad, ok]), fin()])
    assert res.findings == 2


def test_tool_result_only_replies_always():
    _, client, _, _ = go([multi_tool_turn([("echo", {"reason": R}, "a"), ("nope", {}, "b")]), echo(3), fin()])
    for req in client.calls:
        msgs = req["messages"]
        for i, m in enumerate(msgs):
            if m["role"] == "assistant" and any(b["type"] == "tool_use" for b in m["content"]):
                nxt = msgs[i + 1]
                assert nxt["role"] == "user" and isinstance(nxt["content"], list)
                assert all(b["type"] == "tool_result" for b in nxt["content"])


def test_unknown_tool_and_bad_reason_are_error_results_not_crashes():
    res, client, log, _ = go([multi_tool_turn([("nope", {"reason": R}, "a"), ("echo", {"reason": "short"}, "b")]), fin()])
    blocks = client.calls[1]["messages"][-1]["content"]
    assert all(b.get("is_error") for b in blocks)
    assert json.loads(blocks[0]["content"])["error"]["code"] == "not_found"
    assert json.loads(blocks[1]["content"])["error"]["code"] == "invalid_input"
    assert res.status == "finished"


# ---- end_turn handling -----------------------------------------------------------------------
def test_end_turn_nudges_once_then_no_finish():
    res, client, log, _ = go([text_turn("all done"), text_turn("really done")])
    assert res.status == "no_finish" and res.calls == 2
    assert client.calls[1]["messages"][-1] == {"role": "user", "content": NUDGE}


def test_nudge_then_recovery():
    res, _, _, _ = go([text_turn("hmm"), fin()])
    assert res.status == "finished" and res.calls == 2


def test_empty_end_turn_is_not_appended():
    res, client, _, _ = go([raw_turn([], "end_turn"), fin()])
    msgs = client.calls[1]["messages"]
    assert res.status == "finished"
    assert [m["role"] for m in msgs] == ["user", "user"] and msgs[-1]["content"] == NUDGE


# ---- truncation and odd stops ----------------------------------------------------------------
def test_max_tokens_retries_same_request_with_double_limit():
    cut = raw_turn([{"type": "text", "text": "partial"}], "max_tokens", out=4096)
    res, client, _, _ = go([cut, fin()])
    assert res.status == "finished" and res.calls == 2
    assert client.calls[0]["messages"] == client.calls[1]["messages"]
    assert client.calls[1]["max_tokens"] == 2 * client.calls[0]["max_tokens"]


def test_max_tokens_limit_resets_after_success():
    cut = raw_turn([{"type": "text", "text": "partial"}], "max_tokens")
    _, client, _, _ = go([cut, echo(1), echo(2), fin()])
    assert [c["max_tokens"] for c in client.calls] == [4096, 8192, 4096, 4096]


def test_repeated_max_tokens_is_output_truncated():
    cut = lambda: raw_turn([{"type": "text", "text": "partial"}], "max_tokens")
    res, _, _, _ = go([cut(), cut()])
    assert res.status == "output_truncated" and res.calls == 2


@pytest.mark.parametrize("stop,status", [("refusal", "refusal"), ("model_context_window_exceeded", "context_exceeded"),
                                         ("pause_turn", "protocol_error"), ("stop_sequence", "protocol_error")])
def test_other_stop_reasons(stop, status):
    res, _, _, _ = go([raw_turn([{"type": "text", "text": "x"}], stop)])
    assert res.status == status


def test_fatal_llm_error():
    res, _, log, _ = go([echo(1), FatalLLMError("auth", "bad key")])
    assert res.status == "llm_fatal" and "auth" in res.detail and res.calls == 1


# ---- limits ----------------------------------------------------------------------------------
def test_max_calls_is_exact():
    res, client, _, _ = go([echo(i) for i in range(10)], limits=Limits(max_calls=3))
    assert res.status == "max_calls" and res.calls == 3 and len(client.calls) == 3


def test_token_budget():
    res, _, _, _ = go([echo(i) for i in range(10)], limits=Limits(max_total_tokens=300))
    assert res.status == "token_budget" and res.calls == 2 and res.input_tokens + res.output_tokens == 300


def test_cost_budget():
    res, _, _, _ = go([echo(i) for i in range(10)], limits=Limits(max_cost_usd=Decimal("0.0007")))
    assert res.status == "cost_budget" and res.calls == 2 and res.cost_usd == Decimal("0.00070")


def test_unknown_cost_is_not_enforced_and_is_reported_none():
    script = [tool_turn("echo", {"reason": R}, call_id="t1", alias="demo"), tool_turn("finish_review", FIN, call_id="t2", alias="demo")]
    res, _, log, _ = go(script, alias="demo", limits=Limits(max_cost_usd=Decimal("0.0000001")))
    assert res.status == "finished" and res.cost_usd is None
    assert log.events[-1]["cost_known"] is False


def test_wall_time_with_injected_clock():
    ticks = iter(range(0, 10_000, 400))
    res, _, _, _ = go([echo(i) for i in range(10)], limits=Limits(max_wall_s=900), clock=lambda: next(ticks))
    assert res.status == "wall_time"


def test_check_limits_order():
    st = RunState(calls=99, input_tokens=10**7, elapsed_s=10**6, cost_usd=Decimal("99"))
    lim = Limits()
    assert check_limits(st, lim, True) == "killed"
    assert check_limits(st, lim, False) == "wall_time"
    st.elapsed_s = 0
    assert check_limits(st, lim, False) == "max_calls"
    st.calls = 0
    assert check_limits(st, lim, False) == "token_budget"
    st.input_tokens = 0
    assert check_limits(st, lim, False) == "cost_budget"
    st.cost_usd = Decimal("0")
    assert check_limits(st, lim, False) is None


# ---- kill switch -----------------------------------------------------------------------------
def test_kill_before_start_makes_no_model_call():
    k = KillSwitch(path="/nonexistent/kill")
    k.trigger("test")
    res, client, _, _ = go([echo(1)], kill=k)
    assert res.status == "killed" and res.calls == 0 and client.calls == []


def test_kill_during_a_tool_stops_before_the_next_call():
    k = KillSwitch(path="/nonexistent/kill")
    reg = make([ToolSpec("pull", "p", {}, lambda c, a: (k.trigger("mid-run"), {"rows": []})[1])])
    res, client, _, _ = go([tool_turn("pull", {"reason": R}), echo(2)], kill=k, registry=reg)
    assert res.status == "killed" and res.calls == 1 and res.tool_calls == 1 and "mid-run" in res.detail


def test_kill_between_parallel_tools_skips_the_rest():
    k = KillSwitch(path="/nonexistent/kill")
    reg = make([ToolSpec("pull", "p", {}, lambda c, a: (k.trigger("x"), {"rows": []})[1])])
    res, _, _, _ = go([multi_tool_turn([("pull", {"reason": R}, "a"), ("echo", {"reason": R}, "b")])], kill=k, registry=reg)
    assert res.status == "killed" and res.tool_calls == 1


def test_kill_file(tmp_path):
    f = tmp_path / "kill"
    k = KillSwitch(path=f)
    assert not k.is_set()
    f.write_text("")
    res, _, _, _ = go([echo(1)], kill=k)
    assert res.status == "killed" and "kill file" in res.detail


# ---- failure handling ------------------------------------------------------------------------
def test_internal_error_streak_aborts():
    res, _, _, _ = go([tool_turn("boom", {"reason": R}, call_id=f"b{i}") for i in range(5)])
    assert res.status == "tool_failure" and res.tool_calls == 3


def test_internal_error_streak_resets_on_success():
    boom = lambda i: tool_turn("boom", {"reason": R}, call_id=f"b{i}")
    res, _, _, _ = go([boom(1), boom(2), echo(3), boom(4), boom(5), fin()])
    assert res.status == "finished"


def test_closed_database_connection_ends_run():
    ctx = ToolContext(Conn(), "run-1", "gl_sentinel", dry_run=True)
    reg = make([ToolSpec("drop", "d", {}, lambda c, a: (setattr(c.conn, "closed", True), {"rows": []})[1])])
    res, client, _, _ = go([tool_turn("drop", {"reason": R}), echo(2)], ctx=ctx, registry=reg)
    assert res.status == "db_error" and res.calls == 1


# ---- log -------------------------------------------------------------------------------------
def test_log_is_valid_jsonl_with_reasons_and_no_secrets(tmp_path):
    p = tmp_path / "run.jsonl"
    log = RunLog(p)
    client = FakeClient([echo(1), fin()])
    ctx = ToolContext(Conn(), "run-9", "gl_sentinel", dry_run=True)
    run_agent(client, make(), ctx, "system text", "Do the review.", log=log, kill=KillSwitch(path="/nonexistent/kill"))
    log.close()
    lines = [json.loads(x) for x in p.read_text().splitlines()]
    assert [x["seq"] for x in lines] == list(range(1, len(lines) + 1))
    assert lines[0]["event"] == "run_start" and lines[-1]["event"] == "run_end"
    assert lines[-1]["status"] == "finished" and lines[0]["run_id"] == "run-9"
    tools = [x for x in lines if x["event"] == "tool_call"]
    assert tools[0]["reason"] == R and tools[0]["name"] == "echo" and tools[0]["ok"] is True
    text = p.read_text().lower()
    assert "api_key" not in text and "password" not in text and "sk-ant" not in text
    assert "system text" not in text          # the system prompt is logged as a hash, not in full


def test_run_log_survives_a_crash_mid_run(tmp_path):
    p = tmp_path / "run.jsonl"
    log = RunLog(p)
    log.event("run_start", x=1)
    assert json.loads(p.read_text().splitlines()[0])["event"] == "run_start"   # flushed before close


# ---- real tools ------------------------------------------------------------------------------
def test_integration_with_real_gl_sentinel_tools(ctx):
    from fia_tools.registry import build_registry
    reg = build_registry("gl_sentinel")
    script = [tool_turn("describe_data", {"reason": "Orientation first, as the prompt says."}, call_id="d1"),
              tool_turn("finish_review", {"reason": "Nothing more to check in this test.",
                                          "summary": "Test run of the loop with real tools.",
                                          "checked": ["orientation only"]}, call_id="d2")]
    client = FakeClient(script)
    log = RunLog(keep=True)
    res = run_agent(client, reg, ctx, "system", "Review the books.", log=log, kill=KillSwitch(path="/nonexistent/kill"))
    assert res.status == "finished" and res.tool_calls == 2 and res.finish["checked"] == ["orientation only"]
    first = json.loads(client.calls[1]["messages"][-1]["content"][0]["content"])
    assert first["ok"] is True
