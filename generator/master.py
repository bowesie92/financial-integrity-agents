"""Master data: sites, users, accounts, periods, vendors."""
from datetime import date, timedelta

from . import config as C
from .calendar_util import month_bounds, nth_business_day_after, to_utc_iso

_PREFIX = ["Desert", "Canyon", "Mesa", "Saguaro", "Lone Star", "Valley", "Summit", "Pioneer",
           "Redwood", "Cactus", "Sierra", "Prairie", "Copper", "Ironwood", "Blue Sky", "Frontier",
           "Granite", "Cottonwood", "Horizon", "Mission"]
_TRADE = ["Fasteners", "Electrical", "Plumbing Supply", "Tool & Die", "Industrial Gases",
          "Packaging", "Lumber", "Hardware", "Safety Products", "Fleet Services", "Janitorial",
          "Steel", "Paint & Coatings", "Logistics", "Pallet Co", "Abrasives", "HVAC Parts",
          "Lighting", "Equipment Rental", "Office Products", "Printing", "Pest Control",
          "Waste Services", "Uniforms", "Truck Parts"]
_SUFFIX = ["LLC", "Inc", "Co", "Group", "Partners"]
_STREETS = ["Industrial Blvd", "Commerce Dr", "Main St", "Airport Rd", "Warehouse Way",
            "Cesar Chavez Ave", "Elm St", "Technology Pkwy", "Harbor Ln", "Mill Rd"]
# (city, state, zip prefix)
_PLACES = [("Phoenix", "AZ", "850"), ("Tempe", "AZ", "852"), ("Mesa", "AZ", "852"),
           ("Chandler", "AZ", "852"), ("Tucson", "AZ", "857"), ("Dallas", "TX", "752"),
           ("Fort Worth", "TX", "761"), ("Irving", "TX", "750"), ("Fresno", "CA", "937"),
           ("Clovis", "CA", "936"), ("Bakersfield", "CA", "933"), ("Los Angeles", "CA", "900")]


def build_master(ds):
    t = ds.tables
    for sid, name, state, tz in C.SITES:
        t["sites"].append({"site_id": sid, "name": name, "state": state, "timezone": tz})
    for uid, name, role, sid in C.USERS:
        t["users"].append({"user_id": uid, "full_name": name, "role": role,
                           "site_id": sid, "active": True})
    for aid, name, cls in C.ACCOUNTS:
        t["accounts"].append({"account_id": aid, "name": name, "account_class": cls,
                              "active": True})
    for month in range(1, 13):
        start, end = month_bounds(C.YEAR, month)
        t["periods"].append({"period_id": f"{C.YEAR}-{month:02d}",
                             "start_date": start.isoformat(), "end_date": end.isoformat(),
                             "close_date": nth_business_day_after(end, 5).isoformat()})
    start, end = month_bounds(2026, 1)
    t["periods"].append({"period_id": "2026-01", "start_date": start.isoformat(),
                         "end_date": end.isoformat(),
                         "close_date": nth_business_day_after(end, 5).isoformat()})
    _vendors(ds)


def _vendors(ds):
    rng = ds.rng("vendors")
    clerks = [u for u, _, role, _ in C.USERS if role == "ap_clerk"]
    names = set()
    while len(names) < C.N_VENDORS:
        names.add(f"{rng.choice(_PREFIX)} {rng.choice(_TRADE)} {rng.choice(_SUFFIX)}")
    names = sorted(names)
    rng.shuffle(names)
    new_ids = set(rng.sample(range(C.N_VENDORS), C.N_NEW_VENDORS_2025))
    for i, name in enumerate(names):
        city, state, zip3 = rng.choice(_PLACES)
        if i in new_ids:
            created = date(2025, 1, 1) + timedelta(days=rng.randint(30, 300))
        else:
            created = date(2018, 1, 1) + timedelta(days=rng.randint(0, 2300))
        while created.weekday() >= 5:
            created += timedelta(days=1)
        ds.tables["vendors"].append({
            "vendor_id": f"V{i + 1:04d}", "name": name,
            "address": f"{rng.randint(100, 9899)} {rng.choice(_STREETS)}",
            "city": city, "state": state, "postal_code": f"{zip3}{rng.randint(0, 99):02d}",
            "created_at": to_utc_iso(created, rng.randint(8, 16), rng.randint(0, 59), 0,
                                     "America/Phoenix"),
            "created_by": rng.choice(clerks), "active": True})
    ds.meta["new_vendor_ids"] = sorted(f"V{i + 1:04d}" for i in new_ids)
