"""Business calendar helpers. Local time rules come from each site's own time zone."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import HOLIDAYS

UTC = timezone.utc


def is_business_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def month_bounds(year, month):
    start = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return start, nxt - timedelta(days=1)


def business_days(start, end):
    d, out = start, []
    while d <= end:
        if is_business_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def nth_business_day_after(d, n):
    """The n-th business day strictly after d."""
    count = 0
    while count < n:
        d += timedelta(days=1)
        if is_business_day(d):
            count += 1
    return d


def to_utc_iso(local_date, hour, minute, second, tz_name):
    local = datetime(local_date.year, local_date.month, local_date.day,
                     hour, minute, second, tzinfo=ZoneInfo(tz_name))
    return local.astimezone(UTC).isoformat()
