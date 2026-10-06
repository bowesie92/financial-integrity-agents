"""Business rules the tools report and apply. A test pins these to generator/config.py."""
from datetime import date

BUSINESS_START_HOUR = 7    # local time, inclusive
BUSINESS_END_HOUR = 19     # local time, exclusive
BUSINESS_DAYS = "Monday to Friday"
CONTROLLER_LIMIT = 5_000
CFO_LIMIT = 25_000

HOLIDAYS = (
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 5, 26),
    date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 10, 13),
    date(2025, 11, 11), date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19),
)
