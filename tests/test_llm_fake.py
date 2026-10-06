import pytest

from fia_llm import FakeClient, FatalLLMError, ProfileError, text_turn, tool_turn

TOOL = {"name": "echo", "description": "d",
        "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}},
                         "required": ["reason"]}}


def run_loop(client, history, max_iters=5):
    """A deliberately tiny loop used only to test the fake. The real loop is task 4.6."""
    for _ in range(max_iters):
        r = client.complete("sys", history, tools=[TOOL])
        history.append(r.assistant_message())
        if not r.tool_calls:
            return r.text
        history.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": "ok"} for c in r.tool_calls]})
    raise RuntimeError("iteration cap")


def test_two_step_run():
    c = FakeClient([tool_turn("echo", {"reason": "r"}, thinking="plan"), text_turn("done")])
    assert run_loop(c, [{"role": "user", "content": "go"}]) == "done"
    assert len(c.calls) == 2 and c.calls[1]["messages"][1]["content"][0]["type"] == "thinking"


def test_exhausted_script_is_loud():
    c = FakeClient([tool_turn("echo", {"reason": "r"})])
    with pytest.raises(AssertionError, match="exhausted"):
        run_loop(c, [{"role": "user", "content": "go"}])


def test_editing_history_is_caught():
    c = FakeClient([tool_turn("echo", {"reason": "r"}, thinking="plan"), text_turn("done")])
    h = [{"role": "user", "content": "go"}]
    r = c.complete("sys", h, tools=[TOOL])
    msg = r.assistant_message()
    msg["content"] = [b for b in msg["content"] if b["type"] != "thinking"]  # dropped thinking
    h += [msg, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_fake_1", "content": "ok"}]}]
    with pytest.raises(AssertionError, match="appended exactly"):
        c.complete("sys", h, tools=[TOOL])


def test_rewriting_earlier_message_is_caught():
    c = FakeClient([tool_turn("echo", {"reason": "r"}), text_turn("done")])
    h = [{"role": "user", "content": "go"}]
    r = c.complete("sys", h, tools=[TOOL])
    h2 = [{"role": "user", "content": "GO"}, r.assistant_message(),
          {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_fake_1", "content": "ok"}]}]
    with pytest.raises(AssertionError, match="edited"):
        c.complete("sys", h2, tools=[TOOL])


def test_contract_is_enforced_at_zero_cost():
    c = FakeClient([text_turn("x")], alias="demo-plus")
    with pytest.raises(ProfileError):
        c.complete("sys", [{"role": "user", "content": "go"}], thinking="disabled")
    with pytest.raises(ProfileError):
        c.complete("sys", [{"role": "user", "content": "go"}, {"role": "assistant", "content": "{"}])


def test_scripted_error_is_raised():
    c = FakeClient([FatalLLMError("usage_limit", "stop")])
    with pytest.raises(FatalLLMError):
        c.complete("sys", [{"role": "user", "content": "go"}])
