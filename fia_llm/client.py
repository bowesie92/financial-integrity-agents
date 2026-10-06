"""LLMClient: one place that talks to a provider. Anthropic API only for now; Bedrock arrives
at task B7 behind the same interface."""
import os
import time
from typing import Protocol

from .errors import FatalLLMError, classify_http_error
from .profiles import build_request, get_profile
from .types import LLMResult, parse_response

MAX_ATTEMPTS = 4  # first try plus three retries


class LLMClient(Protocol):
    provider: str
    profile: object

    def complete(self, system, messages, tools=(), max_tokens=2048,
                 thinking=None, effort=None) -> LLMResult: ...


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, profile, api_key=None, sdk=None, sleep=time.sleep):
        self.profile = profile
        self._sleep = sleep
        if sdk is None:
            import anthropic  # imported late so tests and the fake client need no SDK
            self._anthropic = anthropic
            # max_retries=0: this class owns the retry policy, so SDK retries would hide it
            sdk = anthropic.Anthropic(api_key=api_key, max_retries=0)
        else:
            self._anthropic = None
        self._sdk = sdk

    def complete(self, system, messages, tools=(), max_tokens=2048, thinking=None, effort=None):
        req = build_request(self.profile, system, messages, tools, max_tokens, thinking, effort)
        settings = {"provider": self.provider, "model": self.profile.model_id,
                    "alias": self.profile.alias, "max_tokens": max_tokens,
                    "thinking": req.get("thinking"), "effort": (req.get("output_config") or {}).get("effort"),
                    "strict_tools": self.profile.strict_tools, "tool_choice": req.get("tool_choice")}
        for attempt in range(MAX_ATTEMPTS):
            try:
                raw = self._sdk.messages.with_raw_response.create(**req)
            except Exception as exc:  # classified below; anything unexpected is fatal
                status, text, retry_after = self._describe(exc)
                if status is None and not self._is_network(exc):
                    raise FatalLLMError("unexpected", f"{type(exc).__name__}: {exc}") from exc
                v = classify_http_error(status, text, retry_after, attempt)
                if v.action == "fatal":
                    raise FatalLLMError(v.kind, text[:300], status) from exc
                if attempt == MAX_ATTEMPTS - 1:
                    raise FatalLLMError("retries_exhausted", f"{v.kind}: {text[:200]}", status) from exc
                self._sleep(v.wait_s)
                continue
            resp = raw.parse()
            h = raw.headers
            return parse_response(self.profile, resp, settings,
                                  request_id=h.get("request-id"),
                                  workspace_id=h.get("anthropic-workspace-id"))

    @staticmethod
    def _is_network(exc):
        return type(exc).__name__ in ("APIConnectionError", "APITimeoutError")

    @staticmethod
    def _describe(exc):
        status = getattr(exc, "status_code", None)
        resp = getattr(exc, "response", None)
        ra = None
        if resp is not None:
            try:
                ra = float(resp.headers.get("retry-after"))
            except (TypeError, ValueError):
                ra = None
        body = getattr(exc, "body", None)
        return status, f"{type(exc).__name__} {body} {exc}", ra


def make_client(env=None, sdk=None):
    """Build a client from configuration only: LLM_PROVIDER, LLM_MODEL (alias), LLM_STRICT_TOOLS."""
    env = os.environ if env is None else env
    provider = env.get("LLM_PROVIDER", "anthropic").strip().lower()
    strict = env.get("LLM_STRICT_TOOLS")
    profile = get_profile(env.get("LLM_MODEL", "dev"),
                          None if strict is None else strict.strip() == "1")
    if provider == "anthropic":
        return AnthropicClient(profile, sdk=sdk)
    raise NotImplementedError(f"Provider {provider!r} is added at task B7")
