import pytest
from types import SimpleNamespace as NS

from fia_llm import (AnthropicClient, FatalLLMError, ProfileError, build_request, check_request,
                     classify_http_error, get_profile, make_client, parse_response)

TOOL = {"name": "t", "description": "d",
        "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}},
                         "required": ["reason"], "additionalProperties": False}}
MSG = [{"role": "user", "content": "hi"}]


def req(alias, **kw):
    return build_request(get_profile(alias), "sys", MSG, **kw)


def test_haiku_is_plain():
    r = req("dev", tools=[TOOL])
    assert r["model"] == "claude-haiku-4-5-20251001"
    assert "thinking" not in r and "output_config" not in r
    assert r["tool_choice"] == {"type": "auto"}


@pytest.mark.parametrize("kw", [{"thinking": "between_tools"}, {"thinking": "adaptive"},
                                {"thinking": "disabled"}, {"effort": "low"}])
def test_haiku_rejects_thinking_and_effort(kw):
    with pytest.raises(ProfileError):
        req("dev", **kw)


def test_sonnet5_allows_disabled_but_no_effort():
    assert req("demo", thinking="disabled")["thinking"] == {"type": "disabled"}
    with pytest.raises(ProfileError):
        req("demo", effort="high")


def test_sonnet55_rules():
    assert req("demo-plus", thinking="between_tools", effort="high")["thinking"] == {"type": "between_tools"}
    assert req("demo-plus", thinking="adaptive_summarized")["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert req("demo-plus", thinking="adaptive", effort="max")["output_config"] == {"effort": "max"}
    with pytest.raises(ProfileError):
        req("demo-plus", thinking="disabled")
    with pytest.raises(ProfileError):
        req("demo-plus", thinking="between_tools", effort="xhigh")
    with pytest.raises(ProfileError):
        req("demo-plus", effort="extreme")


def test_builder_has_no_way_to_pass_forbidden_settings():
    for bad in ("temperature", "top_p", "top_k", "tool_choice", "prefill"):
        with pytest.raises(TypeError):
            build_request(get_profile("dev"), "s", MSG, **{bad: 1})


def test_second_layer_catches_forbidden_fields():
    p = get_profile("demo-plus")
    base = {"messages": MSG}
    for extra in ({"temperature": 0.2}, {"top_k": 5}, {"tool_choice": {"type": "any"}},
                  {"tool_choice": {"type": "tool", "name": "t"}},
                  {"thinking": {"type": "enabled", "budget_tokens": 1000}},
                  {"thinking": {"type": "between_tools", "display": "summarized"}},
                  {"thinking": {"type": "disabled"}}):
        with pytest.raises(ProfileError):
            check_request(p, {**base, **extra})


def test_prefill_rejected():
    with pytest.raises(ProfileError):
        build_request(get_profile("dev"), "s", MSG + [{"role": "assistant", "content": "{"}])


def test_max_tokens_required_and_capped():
    with pytest.raises(ProfileError):
        req("dev", max_tokens=0)
    with pytest.raises(ProfileError):
        req("dev", max_tokens=64_001)


def test_tool_must_require_reason():
    bad = {**TOOL, "input_schema": {"type": "object", "properties": {}, "required": []}}
    with pytest.raises(ProfileError):
        req("dev", tools=[bad])


def test_strict_flag_is_opt_in():
    assert "strict" not in req("dev", tools=[TOOL])["tools"][0]
    r = build_request(get_profile("dev", strict_tools=True), "s", MSG, tools=[TOOL])
    assert r["tools"][0]["strict"] is True


def test_unknown_alias():
    with pytest.raises(ProfileError):
        get_profile("opus")


@pytest.mark.parametrize("status,text,ra,action,kind", [
    (429, "rate_limit_error", 7, "retry", "rate_limit"),
    (429, "rate_limit_error", None, "fatal", "rate_limit_without_retry_after"),
    (429, "enforced_spend_limit_reached", 5, "fatal", "enforced_spend_limit"),
    (400, "You have reached your specified API usage limits", None, "fatal", "usage_limit"),
    (400, "Your credit balance is too low", None, "fatal", "credit_balance"),
    (401, "authentication_error", None, "fatal", "auth"),
    (403, "permission_error", None, "fatal", "auth"),
    (400, "invalid_request_error: something", None, "fatal", "bad_request"),
    (529, "overloaded_error", None, "retry", "server_or_network"),
    (500, "api_error", None, "retry", "server_or_network"),
    (None, "APIConnectionError", None, "retry", "server_or_network"),
    (429, "rate_limit_error", 999, "fatal", "retry_after_too_long"),
])
def test_classify(status, text, ra, action, kind):
    v = classify_http_error(status, text, ra)
    assert (v.action, v.kind) == (action, kind)


# ---- fake SDK -------------------------------------------------------------------------------
class Block:
    def __init__(self, **d):
        self.d = d

    def model_dump(self, mode="json", exclude_none=True):
        return dict(self.d)


def response(blocks, stop="end_turn"):
    usage = NS(input_tokens=1000, output_tokens=500, cache_read_input_tokens=0,
               cache_creation_input_tokens=0)
    return NS(content=blocks, stop_reason=stop, usage=usage, model="claude-haiku-4-5-20251001")


class Raw:
    def __init__(self, resp):
        self.resp, self.headers = resp, {"request-id": "req_1", "anthropic-workspace-id": "wrkspc_1"}

    def parse(self):
        return self.resp


class Err(Exception):
    def __init__(self, status, body="", retry_after=None):
        super().__init__(body)
        self.status_code, self.body = status, body
        self.response = NS(headers={} if retry_after is None else {"retry-after": str(retry_after)})


class FakeSDK:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = NS(with_raw_response=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return Raw(item)


def client(script, alias="dev"):
    sleeps = []
    sdk = FakeSDK(script)
    return AnthropicClient(get_profile(alias), sdk=sdk, sleep=sleeps.append), sdk, sleeps


def test_complete_normalizes_and_keeps_blocks():
    blocks = [Block(type="thinking", thinking="hmm", signature="sig"),
              Block(type="text", text="ok "),
              Block(type="tool_use", id="tu_1", name="t", input={"reason": "x"})]
    c, sdk, _ = client([response(blocks, "tool_use")])
    r = c.complete("sys", MSG, tools=[TOOL])
    assert r.text == "ok " and r.thinking == "hmm"
    assert r.tool_calls[0].name == "t" and r.tool_calls[0].input == {"reason": "x"}
    assert r.stop_reason == "tool_use" and r.request_id == "req_1" and r.workspace_id == "wrkspc_1"
    assert [b["type"] for b in r.assistant_message()["content"]] == ["thinking", "text", "tool_use"]
    assert r.assistant_message()["content"][0]["signature"] == "sig"
    assert str(r.cost_usd) == "0.0035"  # 1000 in at $1, 500 out at $5 per million
    assert r.usage.input_tokens == 1000
    assert "api_key" not in repr(r.settings)


def test_retry_after_then_success():
    c, sdk, sleeps = client([Err(429, "rate_limit_error", 3), response([Block(type="text", text="a")])])
    assert c.complete("s", MSG).text == "a"
    assert sleeps == [3.0] and len(sdk.calls) == 2


def test_fatal_errors_raise_without_retry():
    for status, body in [(429, "enforced_spend_limit_reached"), (400, "reached your specified API usage limits"),
                         (401, "auth")]:
        c, sdk, sleeps = client([Err(status, body, 5)])
        with pytest.raises(FatalLLMError):
            c.complete("s", MSG)
        assert sleeps == [] and len(sdk.calls) == 1


def test_server_errors_back_off_then_give_up():
    c, sdk, sleeps = client([Err(529, "overloaded")] * 4)
    with pytest.raises(FatalLLMError) as e:
        c.complete("s", MSG)
    assert e.value.kind == "retries_exhausted" and len(sdk.calls) == 4 and len(sleeps) == 3


def test_unexpected_exception_is_fatal():
    c, _, _ = client([ValueError("boom")])
    with pytest.raises(FatalLLMError):
        c.complete("s", MSG)


def test_bad_request_never_reaches_sdk():
    c, sdk, _ = client([], alias="demo-plus")
    with pytest.raises(ProfileError):
        c.complete("s", MSG, thinking="disabled")
    assert sdk.calls == []


def test_make_client_from_env():
    c = make_client({"LLM_MODEL": "demo-plus", "LLM_STRICT_TOOLS": "1"}, sdk=FakeSDK([]))
    assert c.profile.model_id == "claude-sonnet-5-5" and c.profile.strict_tools
    with pytest.raises(NotImplementedError):
        make_client({"LLM_PROVIDER": "bedrock"}, sdk=FakeSDK([]))
    assert make_client({}, sdk=FakeSDK([])).profile.alias == "dev"
