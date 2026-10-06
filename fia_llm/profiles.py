"""Model registry and per-model capability profiles.

The request builder is the only place a request is assembled. It cannot be handed
temperature, top_p, top_k, prefill, or a forced tool choice, and check_request() scans the
final dict again as a second layer. Facts verified 2026-10-05 against
platform.claude.com/docs/en/models/sonnet-5-5/migration-guide and the models overview.
"""
from dataclasses import dataclass
from decimal import Decimal

FORBIDDEN_KEYS = ("temperature", "top_p", "top_k", "prefill", "budget_tokens")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
THINKING_MODES = (None, "disabled", "between_tools", "adaptive", "adaptive_summarized")


class ProfileError(ValueError):
    """The request would be rejected (HTTP 400) or break the contract. Raised before sending."""


@dataclass(frozen=True)
class Profile:
    alias: str
    model_id: str
    family: str
    thinking_modes: tuple      # modes the model accepts, None means "omit the field"
    efforts: tuple             # empty means the model takes no effort setting
    max_output_tokens: int | None
    price_in: Decimal | None   # USD per million tokens
    price_out: Decimal | None
    strict_tools: bool = False


_D = Decimal
PROFILES = {
    "dev": Profile("dev", "claude-haiku-4-5-20251001", "haiku-4-5",
                   thinking_modes=(None,), efforts=(), max_output_tokens=64_000,
                   price_in=_D("1"), price_out=_D("5")),
    "demo": Profile("demo", "claude-sonnet-5", "sonnet-5",
                    thinking_modes=(None, "disabled"), efforts=(),  # effort not verified for 5
                    max_output_tokens=None, price_in=None, price_out=None),
    "demo-plus": Profile("demo-plus", "claude-sonnet-5-5", "sonnet-5-5",
                         thinking_modes=(None, "between_tools", "adaptive", "adaptive_summarized"),
                         efforts=EFFORTS, max_output_tokens=128_000,
                         price_in=_D("2"), price_out=_D("10")),
}


def get_profile(alias, strict_tools=None):
    key = (alias or "").strip().lower()
    if key not in PROFILES:
        raise ProfileError(f"Unknown model alias {alias!r}. Known: {', '.join(PROFILES)}")
    p = PROFILES[key]
    if strict_tools is not None:
        p = Profile(**{**p.__dict__, "strict_tools": bool(strict_tools)})
    return p


def _thinking_field(p, mode, effort):
    if mode not in THINKING_MODES:
        raise ProfileError(f"Unknown thinking mode {mode!r}")
    if mode not in p.thinking_modes:
        raise ProfileError(f"{p.alias} ({p.model_id}) does not accept thinking mode {mode!r}")
    if mode is None:
        return None
    if mode == "disabled":
        return {"type": "disabled"}
    if mode == "between_tools":
        return {"type": "between_tools"}        # takes no other fields
    if mode == "adaptive":
        return {"type": "adaptive"}
    return {"type": "adaptive", "display": "summarized"}


def _mark_cache(messages):
    """Copy the messages and put one cache breakpoint on the last block of the last message. The cache
    covers tools, system and every earlier message, so each call re-reads the history at 0.1x the input
    price. The caller's history is not changed. Prompts under the model's minimum (4,096 tokens for
    Haiku 4.5) are simply not cached; the API returns no error."""
    last = messages[-1]
    content = last["content"]
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else [dict(b) for b in content]
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    return [*messages[:-1], {**last, "content": blocks}]


def build_request(profile, system, messages, tools=(), max_tokens=2048,
                  thinking=None, effort=None, require_reason=True, cache=False):
    """Return the keyword arguments for messages.create, or raise ProfileError."""
    if not isinstance(system, str) or not system.strip():
        raise ProfileError("system must be a non-empty string")
    if not messages:
        raise ProfileError("messages is empty")
    if messages[-1].get("role") != "user":
        raise ProfileError("The conversation must end with a user message (no prefill)")
    if not isinstance(max_tokens, int) or max_tokens < 1:
        raise ProfileError("max_tokens must be a positive integer, set on every call")
    if profile.max_output_tokens and max_tokens > profile.max_output_tokens:
        raise ProfileError(f"max_tokens {max_tokens} exceeds {profile.max_output_tokens}")

    req = {"model": profile.model_id, "max_tokens": max_tokens, "system": system,
           "messages": _mark_cache(messages) if cache else list(messages)}

    th = _thinking_field(profile, thinking, effort)
    if th is not None:
        req["thinking"] = th

    if effort is not None:
        if not profile.efforts:
            raise ProfileError(f"{profile.alias} takes no effort setting")
        if effort not in profile.efforts:
            raise ProfileError(f"Unknown effort {effort!r}")
        if thinking == "between_tools" and effort in ("xhigh", "max"):
            raise ProfileError("effort xhigh and max need adaptive thinking, not between_tools")
        req["output_config"] = {"effort": effort}

    if tools:
        out = []
        for t in tools:
            for k in ("name", "description", "input_schema"):
                if k not in t:
                    raise ProfileError(f"Tool {t.get('name', '?')} is missing {k!r}")
            if require_reason and "reason" not in (t["input_schema"].get("required") or []):
                raise ProfileError(f"Tool {t['name']} must require a 'reason' argument")
            d = dict(t)
            if profile.strict_tools:
                d["strict"] = True
            out.append(d)
        req["tools"] = out
        req["tool_choice"] = {"type": "auto"}

    check_request(profile, req)
    return req


def check_request(profile, req):
    """Second layer: scan the finished request for anything the contract forbids."""
    for k in FORBIDDEN_KEYS:
        if k in req or k in (req.get("thinking") or {}):
            raise ProfileError(f"Forbidden field {k!r} in request")
    tc = req.get("tool_choice")
    if tc is not None and tc.get("type") not in ("auto", "none"):
        raise ProfileError(f"tool_choice {tc!r} is not allowed; use auto")
    th = req.get("thinking")
    if th and th.get("type") in ("enabled",):
        raise ProfileError("thinking type 'enabled' is not allowed")
    if th and th.get("type") == "between_tools" and set(th) != {"type"}:
        raise ProfileError("between_tools takes no other fields")
    if th and th.get("type") == "disabled" and profile.family == "sonnet-5-5":
        raise ProfileError("Sonnet 5.5 rejects thinking 'disabled'")
    if req["messages"][-1].get("role") != "user":
        raise ProfileError("The conversation must end with a user message")
    return True
