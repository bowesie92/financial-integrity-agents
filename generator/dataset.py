"""A generated dataset: table rows plus the ground-truth manifest. Written to CSV by write_csv."""
import csv
import json
import random
from pathlib import Path

# Column order for each table, matching db/001_schema.sql (identity columns are left out so
# the database assigns them).
COLUMNS = {
    "sites": ["site_id", "name", "state", "timezone"],
    "users": ["user_id", "full_name", "role", "site_id", "active"],
    "accounts": ["account_id", "name", "account_class", "active"],
    "periods": ["period_id", "start_date", "end_date", "close_date"],
    "journal_entries": ["je_id", "period_id", "entry_date", "posted_at", "posted_by",
                        "approved_by", "source", "description", "site_id"],
    "gl_lines": ["je_id", "account_id", "site_id", "debit", "credit", "memo"],
    "vendors": ["vendor_id", "name", "address", "city", "state", "postal_code",
                "created_at", "created_by", "active"],
    "vendor_bank_changes": ["vendor_id", "changed_at", "changed_by", "old_last4", "new_last4",
                            "verified_by", "verification_note"],
    "purchase_orders": ["po_id", "vendor_id", "site_id", "po_date", "amount", "requested_by",
                        "approved_by"],
    "invoices": ["invoice_id", "vendor_id", "doc_number", "txn_date", "due_date", "total_amt",
                 "po_id", "site_id", "memo", "entered_by", "entered_at", "approved_by",
                 "approved_at"],
    "invoice_lines": ["invoice_id", "line_num", "account_id", "amount", "description"],
    "payments": ["payment_id", "invoice_id", "paid_at", "amount", "bank_last4", "method"],
}

MANIFEST_COLUMNS = ["seed", "kind", "agent", "pattern", "severity", "expected_behavior",
                    "record_refs"]


class Dataset:
    def __init__(self, seed):
        self.seed = seed
        self.tables = {name: [] for name in COLUMNS}
        self.manifest = []   # rows for fia_gt.manifest, written by later stages
        self.meta = {}       # helper facts later stages need (not written to the database)

    def rng(self, name):
        """An independent, repeatable random stream per module, derived from the seed."""
        return random.Random(f"fia:{self.seed}:{name}")


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def write_csv(ds, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for table, cols in COLUMNS.items():
        with open(outdir / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in ds.tables[table]:
                w.writerow([_cell(row.get(c)) for c in cols])
    with open(outdir / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(MANIFEST_COLUMNS)
        for m in ds.manifest:
            w.writerow([ds.seed, m["kind"], m["agent"], m["pattern"], _cell(m["severity"]),
                        m["expected_behavior"], json.dumps(m["record_refs"], sort_keys=True)])
