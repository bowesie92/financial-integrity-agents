"""Pure analytics shared by the GL tools and the rules-only baseline (task 4.5), so the two are
compared on the same arithmetic. No database access here.

Benford bands are Nigrini's published MAD ranges for the first digit (Nigrini, 2012):
below 0.006 close, 0.006 to 0.012 acceptable, 0.012 to 0.015 marginal, above 0.015 nonconforming.
"""
import math
from datetime import timedelta
from decimal import Decimal
from statistics import NormalDist  # noqa: F401  (kept for callers that want p-values)
from zoneinfo import ZoneInfo

from . import constants as K

MIN_BENFORD_SAMPLE = 5000
FIRST_DIGIT_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}
FIRST_TWO_EXPECTED = {p: math.log10(1 + 1 / p) for p in range(10, 100)}
TIMING_RULES = ("weekend", "holiday", "after_hours", "post_close", "last_3_days_of_period")


def first_digit(amount):
    """First significant digit of an amount of at least 1.00, as the database computes it."""
    s = f"{abs(Decimal(str(amount))):.2f}"
    return int(s[0]) if float(amount) >= 1 else None


def first_two_digits(amount):
    s = f"{abs(Decimal(str(amount))):.2f}".replace(".", "")
    return int(s[:2]) if float(amount) >= 1 else None


def is_round_multiple(amount, base=1000):
    return Decimal(str(amount)) % base == 0


def mad_band(mad):
    if mad < 0.006:
        return "close"
    if mad < 0.012:
        return "acceptable"
    if mad < 0.015:
        return "marginal"
    return "nonconforming"


def first_digit_stats(counts):
    """counts: {digit: n} for digits 1 to 9."""
    n = sum(counts.get(d, 0) for d in range(1, 10))
    if n == 0:
        return {"n": 0, "digits": [], "mad": None, "band": None, "sufficient_sample": False,
                "minimum_sample": MIN_BENFORD_SAMPLE}
    rows, total = [], 0.0
    for d in range(1, 10):
        obs = counts.get(d, 0) / n
        total += abs(obs - FIRST_DIGIT_EXPECTED[d])
        rows.append({"digit": d, "observed_count": counts.get(d, 0), "observed_share": round(obs, 4),
                     "expected_share": round(FIRST_DIGIT_EXPECTED[d], 4)})
    mad = total / 9
    return {"n": n, "digits": rows, "mad": round(mad, 4), "band": mad_band(mad),
            "sufficient_sample": n >= MIN_BENFORD_SAMPLE, "minimum_sample": MIN_BENFORD_SAMPLE}


def first_two_stats(counts, top=10):
    """counts: {pair: n} for pairs 10 to 99. Ranks pairs by absolute z-statistic (with continuity
    correction) and says whether each is in excess or deficit."""
    n = sum(counts.get(p, 0) for p in range(10, 100))
    if n == 0:
        return {"n": 0, "pairs": [], "sufficient_sample": False, "minimum_sample": MIN_BENFORD_SAMPLE}
    out = []
    for p in range(10, 100):
        e = FIRST_TWO_EXPECTED[p]
        obs = counts.get(p, 0) / n
        z = (abs(obs - e) - 1 / (2 * n)) / math.sqrt(e * (1 - e) / n)
        out.append({"digits": p, "observed_count": counts.get(p, 0), "expected_count": round(e * n, 1),
                    "z": round(max(z, 0.0), 2), "direction": "excess" if obs > e else "deficit"})
    out.sort(key=lambda r: (-r["z"], r["digits"]))
    return {"n": n, "pairs": out[:top], "sufficient_sample": n >= MIN_BENFORD_SAMPLE,
            "minimum_sample": MIN_BENFORD_SAMPLE}


def orders_of_magnitude(lo, hi):
    return round(math.log10(float(hi) / float(lo)), 1) if lo and hi and float(lo) > 0 else 0.0


def timing_flags(posted_at, tz_name, period_end, close_date):
    """Which timing rules an entry trips. Times are judged in the poster's local time."""
    local = posted_at.astimezone(ZoneInfo(tz_name))
    d, flags = local.date(), []
    if local.weekday() >= 5:
        flags.append("weekend")
    if d in K.HOLIDAYS:
        flags.append("holiday")
    if not K.BUSINESS_START_HOUR <= local.hour < K.BUSINESS_END_HOUR:
        flags.append("after_hours")
    if d > close_date:
        flags.append("post_close")
    if period_end - timedelta(days=2) <= d <= period_end:
        flags.append("last_3_days_of_period")
    return flags
