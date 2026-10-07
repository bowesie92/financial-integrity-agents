"""The few facts the scorer needs from the data itself: who posted an entry, which accounts it touched,
what an invoice totals, and when a vendor was created. Two versions give the same answers:
GeneratorLookups reads the freshly generated dataset (used by the tests, no database needed) and
DbLookups reads the real database through the admin role (used by scripts/evaluate.py)."""
from decimal import Decimal


class GeneratorLookups:
    available = True

    def __init__(self, ds):
        t = ds.tables
        self._je = {r["je_id"]: r for r in t["journal_entries"]}
        self._users = {r["user_id"]: r["full_name"] for r in t["users"]}
        self._lines = {}
        for r in t["gl_lines"]:
            self._lines.setdefault(r["je_id"], set()).add(r["account_id"])
        self._inv = {r["invoice_id"]: Decimal(str(r["total_amt"])) for r in t["invoices"]}
        self._ven = {r["vendor_id"]: str(r["created_at"])[:10] for r in t["vendors"]}

    def posters(self, je_ids):
        return {j: (self._je[j]["posted_by"], self._users.get(self._je[j]["posted_by"], "")) for j in je_ids if j in self._je}

    def je_accounts(self, je_ids):
        return set().union(*(self._lines.get(j, set()) for j in je_ids)) if je_ids else set()

    def invoice_totals(self, ids):
        return {i: self._inv[i] for i in ids if i in self._inv}

    def vendor_created(self, vendor_id):
        return self._ven.get(vendor_id)


class DbLookups:
    available = True

    def __init__(self, conn):
        self.conn = conn

    def posters(self, je_ids):
        rows = self.conn.execute(
            "select j.je_id, j.posted_by, coalesce(u.full_name, '') from fia.journal_entries j "
            "left join fia.users u on u.user_id = j.posted_by where j.je_id = any(%s)", [list(je_ids)]).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    def je_accounts(self, je_ids):
        rows = self.conn.execute("select distinct account_id from fia.gl_lines where je_id = any(%s)",
                                 [list(je_ids)]).fetchall()
        return {str(r[0]) for r in rows}

    def invoice_totals(self, ids):
        rows = self.conn.execute("select invoice_id, total_amt from fia.invoices where invoice_id = any(%s)",
                                 [list(ids)]).fetchall()
        return {r[0]: Decimal(str(r[1])) for r in rows}

    def vendor_created(self, vendor_id):
        if not vendor_id:
            return None
        row = self.conn.execute("select created_at::date::text from fia.vendors where vendor_id = %s", [vendor_id]).fetchone()
        return row[0] if row else None
