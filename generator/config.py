"""Fixed company facts and volumes. Nothing in this file depends on the seed."""
from datetime import date

COMPANY = "Sonoran Ridge Supply Co."
YEAR = 2025
AS_OF = date(2026, 1, 31)

N_VENDORS = 120
N_NEW_VENDORS_2025 = 12      # vendors created during 2025, the pool for "new vendor" tests
N_CLEAN_JES = 14_400         # random everyday entries; planted and recurring entries come on top
BUSINESS_START_HOUR = 7      # local time, inclusive
BUSINESS_END_HOUR = 19       # local time, exclusive

CONTROLLER_LIMIT = 5_000     # approval needed from the controller at or above this
CFO_LIMIT = 25_000           # approval needed from the CFO at or above this

# (site_id, name, state, IANA time zone). Arizona has no daylight saving time.
SITES = [
    (1, "Phoenix HQ", "AZ", "America/Phoenix"),
    (2, "Dallas Branch", "TX", "America/Chicago"),
    (3, "Fresno Branch", "CA", "America/Los_Angeles"),
]

# (user_id, full_name, role, site_id). All names are fictional.
USERS = [
    ("u01", "Dana Whitfield", "controller", 1),
    ("u02", "Marcus Chen", "cfo", 1),
    ("u03", "Priya Raman", "senior_accountant", 1),
    ("u04", "Tomas Herrera", "senior_accountant", 2),
    ("u05", "Elise Okafor", "staff_accountant", 1),
    ("u06", "Brian Kowalski", "staff_accountant", 1),
    ("u07", "Lena Park", "staff_accountant", 1),
    ("u08", "Carlos Mendez", "staff_accountant", 2),
    ("u09", "Hannah Brooks", "staff_accountant", 3),
    ("u10", "Sofia Alvarez", "ap_clerk", 1),
    ("u11", "Derek Nguyen", "ap_clerk", 1),
    ("u12", "Rhonda Fisher", "ap_clerk", 2),
    ("u13", "Jamal Carter", "ap_clerk", 3),
    ("u14", "Greg Sullivan", "buyer", 1),
    ("u15", "Aisha Patel", "buyer", 1),
    ("u16", "Luis Ortega", "buyer", 2),
    ("u17", "Nate Becker", "buyer", 3),
    ("u18", "Walt Dawson", "warehouse", 1),
    ("u19", "Rita Gomez", "warehouse", 2),
    ("u20", "Ken Ito", "warehouse", 3),
    ("u21", "Olivia Grant", "sales", 1),
    ("u22", "Pete Marino", "sales", 2),
    ("u23", "Sam Reyes", "it_admin", 1),
    ("u24", "System Batch", "it_admin", 1),
]
SYSTEM_USER = "u24"
CONTROLLER, CFO = "u01", "u02"
SENIORS = ["u03", "u04"]

# (account_id, name, class)
ACCOUNTS = [
    ("1000", "Cash", "asset"), ("1100", "Accounts receivable", "asset"),
    ("1200", "Inventory", "asset"), ("1300", "Prepaid expenses", "asset"),
    ("1500", "Fixed assets", "asset"), ("1590", "Accumulated depreciation", "asset"),
    ("2000", "Accounts payable", "liability"), ("2100", "Accrued liabilities", "liability"),
    ("2200", "Payroll liabilities", "liability"), ("2300", "Sales tax payable", "liability"),
    ("2500", "Line of credit", "liability"), ("3000", "Owner equity", "equity"),
    ("4000", "Product sales", "revenue"), ("4100", "Service revenue", "revenue"),
    ("4900", "Sales returns", "revenue"),
    ("5000", "Cost of goods sold", "cogs"), ("5100", "Freight in", "cogs"),
    ("5200", "Inventory adjustments", "cogs"),
    ("6000", "Salaries and wages", "expense"), ("6010", "Payroll taxes", "expense"),
    ("6020", "Employee benefits", "expense"), ("6100", "Rent", "expense"),
    ("6110", "Utilities", "expense"), ("6120", "Telephone and internet", "expense"),
    ("6200", "Insurance", "expense"), ("6210", "Repairs and maintenance", "expense"),
    ("6220", "Vehicle and fuel", "expense"), ("6300", "Office supplies", "expense"),
    ("6310", "Warehouse supplies", "expense"), ("6320", "Software subscriptions", "expense"),
    ("6400", "Professional fees", "expense"), ("6410", "Marketing", "expense"),
    ("6420", "Travel and meals", "expense"), ("6430", "Training", "expense"),
    ("6500", "Depreciation", "expense"), ("6510", "Bank fees", "expense"),
    ("6520", "Dues and subscriptions", "expense"), ("6700", "Taxes and licenses", "expense"),
    ("6950", "Miscellaneous adjustments", "expense"),
    ("6960", "Special project consulting", "expense"),
]
# Accounts that few people ever post to. Used as the "seldom-used account" in planted patterns.
SELDOM_ACCOUNTS = ["6950", "6960"]
# Accounts only posted by recurring entries (rent, payroll). Excluded from random postings.
RECURRING_ONLY = ["6000", "6010", "6020", "6100"]

# Holidays treated as non-business days (US federal subset relevant to the data).
HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 5, 26),
    date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1), date(2025, 10, 13),
    date(2025, 11, 11), date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19),
}

# Amounts are drawn log-uniformly inside whole decades, so first digits follow Benford's law
# exactly whatever these weights are. The weights only shape how big amounts tend to be.
DECADE_EXPONENTS = [1, 2, 3, 4, 5]          # $10-$100, $100-$1k, ... $100k-$1M
DECADE_WEIGHTS = [0.20, 0.35, 0.33, 0.10, 0.02]
