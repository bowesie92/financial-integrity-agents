"""Hard limits for one run, and the single function that decides whether a run must stop.

check_limits is the stop policy in one place. It is called before every model call. The order of the
checks is part of the policy (tests pin it): when two limits are hit at once, the first one listed
is the status that gets recorded.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Limits:
    max_calls: int = 40                      # model calls, including a retry after a truncated reply
    max_total_tokens: int = 3_000_000        # input (cached and not) plus output, summed over every call; cost is the main cap
    max_cost_usd: Decimal | None = Decimal("1.50")
    max_wall_s: float = 900.0
    max_output_tokens: int = 4096            # per call; doubled once if a reply is cut off
    max_nudges: int = 1                      # reminders to call finish_review before giving up
    max_recoveries: int = 1                  # times a run may carry on after a reply was cut off twice in a row
    max_internal_errors_in_row: int = 3      # tool failures in a row before the run is abandoned


@dataclass
class RunState:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    cost_known: bool = True                  # False once any call has no price (Sonnet 5)
    elapsed_s: float = 0.0

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens

    def add(self, result):
        """Count one model call. A reply that was cut off still cost money, so it is counted."""
        self.calls += 1
        self.input_tokens += result.usage.total_input_tokens      # cached and uncached
        self.cache_read_tokens += result.usage.cache_read_tokens
        self.cache_write_tokens += result.usage.cache_write_tokens
        self.output_tokens += result.usage.output_tokens
        if result.cost_usd is None:
            self.cost_known = False
        else:
            self.cost_usd += result.cost_usd


def check_limits(state, limits, killed):
    """Return the status to stop with, or None to carry on. Order matters."""
    if killed:
        return "killed"
    if state.elapsed_s >= limits.max_wall_s:
        return "wall_time"
    if state.calls >= limits.max_calls:
        return "max_calls"
    if state.total_tokens >= limits.max_total_tokens:
        return "token_budget"
    if limits.max_cost_usd is not None and state.cost_known and state.cost_usd >= limits.max_cost_usd:
        return "cost_budget"
    return None
