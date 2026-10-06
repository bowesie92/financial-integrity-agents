"""Provider-neutral result shape. `content` keeps every block exactly as returned, so the
loop can append it to history unchanged (thinking blocks included)."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_input_tokens(self):
        """Every input token the call used. The API reports cached tokens separately from input_tokens."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class LLMResult:
    content: tuple          # raw blocks, in order, as dicts
    stop_reason: str
    usage: Usage
    model: str
    request_id: str | None
    workspace_id: str | None
    settings: dict          # the request settings that produced this result (no secrets)
    cost_usd: Decimal | None

    @property
    def text(self):
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")

    @property
    def thinking(self):
        return "".join(b.get("thinking", "") for b in self.content if b.get("type") == "thinking")

    @property
    def tool_calls(self):
        return tuple(ToolCall(b["id"], b["name"], b.get("input") or {})
                     for b in self.content if b.get("type") == "tool_use")

    def assistant_message(self):
        """The message to append to history, blocks untouched."""
        return {"role": "assistant", "content": [dict(b) for b in self.content]}


CACHE_WRITE_MULT = Decimal("1.25")   # 5-minute cache write, times the base input price
CACHE_READ_MULT = Decimal("0.1")     # cache read, times the base input price


def cost_usd(profile, usage):
    """Input, cache writes (1.25x), cache reads (0.1x) and output. None when the model has no price."""
    if profile.price_in is None or profile.price_out is None:
        return None
    return (Decimal(usage.input_tokens) * profile.price_in
            + Decimal(usage.cache_write_tokens) * profile.price_in * CACHE_WRITE_MULT
            + Decimal(usage.cache_read_tokens) * profile.price_in * CACHE_READ_MULT
            + Decimal(usage.output_tokens) * profile.price_out) / Decimal(1_000_000)


def parse_response(profile, resp, settings, request_id=None, workspace_id=None):
    """Turn an SDK response (or any object with the same attributes) into an LLMResult."""
    blocks = []
    for b in resp.content:
        d = b.model_dump(mode="json", exclude_none=True) if hasattr(b, "model_dump") else dict(b)
        blocks.append(d)
    u = resp.usage
    usage = Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )
    return LLMResult(tuple(blocks), resp.stop_reason or "", usage, resp.model, request_id,
                     workspace_id, dict(settings), cost_usd(profile, usage))
