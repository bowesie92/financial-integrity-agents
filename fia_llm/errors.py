"""Error classes. Retry only what the Provider contract says to retry; everything else aborts."""
from dataclasses import dataclass

MAX_RETRY_AFTER_S = 120  # a longer wait than this is treated as fatal, never slept through


class LLMError(Exception):
    pass


class FatalLLMError(LLMError):
    """The run must stop and write an 'aborted' record. Never retried."""

    def __init__(self, kind, message, status=None):
        super().__init__(f"{kind}: {message}")
        self.kind, self.status = kind, status


class RetryableLLMError(LLMError):
    def __init__(self, message, wait_s):
        super().__init__(message)
        self.wait_s = wait_s


@dataclass(frozen=True)
class Verdict:
    action: str          # "retry" or "fatal"
    kind: str
    wait_s: float = 0.0


def classify_http_error(status, text, retry_after=None, attempt=0):
    """Decide what to do with an HTTP error. `text` is the error type plus message, any case.

    attempt is 0 for the first failure and sets the backoff for server errors.
    """
    t = (text or "").lower()
    if "enforced_spend_limit_reached" in t:
        return Verdict("fatal", "enforced_spend_limit")
    if "reached your specified api usage limits" in t:
        return Verdict("fatal", "usage_limit")
    if "credit balance" in t:
        return Verdict("fatal", "credit_balance")
    if status in (401, 403):
        return Verdict("fatal", "auth")
    if status == 429:
        if retry_after is None:
            return Verdict("fatal", "rate_limit_without_retry_after")
        if retry_after > MAX_RETRY_AFTER_S:
            return Verdict("fatal", "retry_after_too_long")
        return Verdict("retry", "rate_limit", float(retry_after))
    if status is None or status >= 500:  # connection problems, 5xx, 529 overloaded
        return Verdict("retry", "server_or_network", float(min(2 ** attempt * 2, 30)))
    return Verdict("fatal", "bad_request")
