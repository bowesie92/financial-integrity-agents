"""Provider-neutral LLM layer. See the Provider contract tab of the Master Plan."""
from .errors import FatalLLMError, RetryableLLMError, classify_http_error
from .profiles import PROFILES, Profile, ProfileError, build_request, check_request, get_profile
from .types import LLMResult, ToolCall, Usage, parse_response
from .client import AnthropicClient, LLMClient, make_client
from .fake import FakeClient, text_turn, tool_turn

__all__ = [
    "FatalLLMError", "RetryableLLMError", "classify_http_error", "PROFILES", "Profile",
    "ProfileError", "build_request", "check_request", "get_profile", "LLMResult", "ToolCall",
    "Usage", "parse_response", "AnthropicClient", "LLMClient", "make_client", "FakeClient", "text_turn", "tool_turn",
]
