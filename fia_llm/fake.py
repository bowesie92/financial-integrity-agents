"""FakeClient: a scripted stand-in for LLMClient so loop logic is tested at zero cost.

It runs every request through the real request builder, so a loop that would send a forbidden
setting or end on an assistant message fails here, not on a paid call. It also enforces the
append-only history rule: each call must extend the previous call's messages with exactly the
assistant blocks it was handed, untouched, followed by new user content.
"""
import copy
from decimal import Decimal

from .profiles import build_request, get_profile
from .types import LLMResult, Usage, cost_usd


def _result(profile, blocks, stop, inp=100, out=50):
    usage = Usage(input_tokens=inp, output_tokens=out)
    return LLMResult(tuple(blocks), stop, usage, profile.model_id, "req_fake", "wrkspc_fake",
                     {"provider": "fake", "model": profile.model_id}, cost_usd(profile, usage))


def text_turn(text, alias="dev", thinking=None):
    """A final answer. `thinking` adds a thinking block first, as Sonnet 5.x may do."""
    blocks = [{"type": "thinking", "thinking": thinking, "signature": "sig_fake"}] if thinking else []
    blocks.append({"type": "text", "text": text})
    return _result(get_profile(alias), blocks, "end_turn")


def tool_turn(name, tool_input, call_id="toolu_fake_1", text="", alias="dev", thinking=None):
    """The model asks for one tool."""
    blocks = [{"type": "thinking", "thinking": thinking, "signature": "sig_fake"}] if thinking else []
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.append({"type": "tool_use", "id": call_id, "name": name, "input": tool_input})
    return _result(get_profile(alias), blocks, "tool_use")


class FakeClient:
    provider = "fake"

    def __init__(self, script, alias="dev", check_history=True):
        self.profile = get_profile(alias)
        self.script = list(script)
        self.calls = []            # deep copies of every request, for assertions
        self._last_result = None
        self._check_history = check_history

    def complete(self, system, messages, tools=(), max_tokens=2048, thinking=None, effort=None):
        req = build_request(self.profile, system, messages, tools, max_tokens, thinking, effort)
        if self._check_history and self.calls:
            prev = self.calls[-1]["messages"]
            if messages[:len(prev)] != prev:
                raise AssertionError("History was edited: earlier messages changed")
            expect = self._last_result.assistant_message()
            if len(messages) <= len(prev) or messages[len(prev)] != expect:
                raise AssertionError("The assistant reply was not appended exactly as returned")
        self.calls.append(copy.deepcopy(req))
        if not self.script:
            raise AssertionError("FakeClient script is exhausted: the loop made an extra call")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        self._last_result = step
        return step
