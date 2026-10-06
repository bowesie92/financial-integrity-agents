"""Runs the real SDK against a mocked HTTP transport: no network, no key, no cost.
Skipped when the anthropic package is not installed."""
import json

import pytest

anthropic = pytest.importorskip("anthropic")
try:  # newer SDK releases ship their own fork named httpx2
    import httpx2 as httpx
except ImportError:
    httpx = pytest.importorskip("httpx")

from fia_llm import AnthropicClient, FatalLLMError, get_profile  # noqa: E402

TOOL = {"name": "t", "description": "d",
        "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}},
                         "required": ["reason"]}}
BODY = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "stop_reason": "tool_use", "stop_sequence": None,
        "content": [{"type": "thinking", "thinking": "plan", "signature": "abc"},
                    {"type": "text", "text": "checking"},
                    {"type": "tool_use", "id": "toolu_1", "name": "t", "input": {"reason": "r"}}],
        "usage": {"input_tokens": 10, "output_tokens": 5}}


def make(handler, alias):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    sdk = anthropic.Anthropic(api_key="test-not-a-key", max_retries=0, http_client=http)
    return AnthropicClient(get_profile(alias), sdk=sdk, sleep=lambda s: None)


def test_wire_body_and_roundtrip():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=BODY, headers={"request-id": "req_9"})

    c = make(handler, "demo-plus")
    r = c.complete("sys", [{"role": "user", "content": "go"}], tools=[TOOL],
                   thinking="between_tools", effort="high", max_tokens=1000)
    b = seen["body"]
    assert b["model"] == "claude-sonnet-5-5" and b["thinking"] == {"type": "between_tools"}
    assert b["output_config"] == {"effort": "high"} and b["tool_choice"] == {"type": "auto"}
    for k in ("temperature", "top_p", "top_k"):
        assert k not in b
    assert r.tool_calls[0].input == {"reason": "r"} and r.request_id == "req_9"
    # History round trip: blocks come back out exactly, signature included, no null fields.
    blocks = r.assistant_message()["content"]
    assert blocks[0] == {"type": "thinking", "thinking": "plan", "signature": "abc"}
    assert all(v is not None for blk in blocks for v in blk.values())


def test_http_errors_map_to_fatal():
    def handler(request):
        return httpx.Response(429, json={"type": "error", "error": {
            "type": "rate_limit_error", "message": "enforced_spend_limit_reached"}})

    with pytest.raises(FatalLLMError) as e:
        make(handler, "dev").complete("s", [{"role": "user", "content": "x"}])
    assert e.value.kind == "enforced_spend_limit"
