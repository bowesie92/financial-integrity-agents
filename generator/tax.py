"""Sales and use tax layer for AP (Phase 3 amendment, decision D24).

Runs after add_ap and only edits existing invoices, so no id, amount, date or earlier manifest
row changes. It uses its own random stream. For every invoice it sets `tax_amt`, the part of
`total_amt` that is sales tax (total_amt already includes it, so line sums still equal totals).

Rules built into the data (state base rates only, local taxes are not modeled):
- Taxable goods: office supplies (6300) and warehouse supplies (6310).
- Inventory (1200) and freight in (5100) are bought for resale or are part of inventory cost.
- An in-state vendor charges the state's base rate on taxable lines.
- A cross-state shipment is an invoice whose site state differs from the vendor's state.
"""
import json
from decimal import ROUND_HALF_UP, Decimal

from . import config as C

RATES = {"AZ": Decimal("0.056"), "TX": Decimal("0.0625"), "CA": Decimal("0.0725")}
TAXABLE = {"6300", "6310"}
RESALE = {"1200", "5100"}
N_PLANTED, N_CHARGED, N_RESALE = 8, 5, 8
MIN_BASE = Decimal("500")      # taxable base needed for the exposure to be worth a finding

MANIFEST_TAX = {
    "use_tax_exposure": ("planted", "low",
        "Flag a cross-state purchase of taxable goods where the vendor charged no tax. Estimate "
        "the use tax owed at the destination state's base rate and cite that state's rule."),
    "cross_state_tax_charged": ("decoy", None,
        "Clear: an out-of-state vendor charged the destination state's tax, so no use tax is "
        "owed on the taxed goods."),
    "cross_state_resale_inventory": ("decoy", None,
        "Clear: inventory bought for resale from an out-of-state vendor is exempt from use tax."),
}


def _cents(x):
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _tax_inside(base, state):
    """Tax contained in a tax-inclusive amount."""
    r = RATES[state]
    return _cents(base * r / (1 + r))


def add_use_tax(ds):
    t = ds.tables
    rng = ds.rng("use_tax")
    state_of_site = {s["site_id"]: s["state"] for s in t["sites"]}
    site_of_state = {v: k for k, v in state_of_site.items()}
    vendor_state = {v["vendor_id"]: v["state"] for v in t["vendors"]}
    lines = {}
    for ln in t["invoice_lines"]:
        lines.setdefault(ln["invoice_id"], []).append(ln)

    busy_inv, busy_vendors = set(), set()
    for m in ds.manifest:
        r = m["record_refs"]
        busy_inv.update(r.get("invoice_ids", []))
        if r.get("vendor_id"):
            busy_vendors.add(r["vendor_id"])
        busy_vendors.update(r.get("vendor_ids", []))

    def accts(i):
        return {ln["account_id"] for ln in lines[i["invoice_id"]]}

    def base(i):
        return sum((C_dec(ln["amount"]) for ln in lines[i["invoice_id"]]
                    if ln["account_id"] in TAXABLE), Decimal("0"))

    free = [i for i in t["invoices"]
            if i["invoice_id"] not in busy_inv and i["vendor_id"] not in busy_vendors
            and not i["po_id"]]
    supply = [i for i in free if accts(i) & TAXABLE and accts(i) <= TAXABLE | RESALE
              and base(i) >= MIN_BASE]
    resale = [i for i in free if accts(i) <= RESALE]
    rng.shuffle(supply)
    rng.shuffle(resale)
    if len(supply) < N_PLANTED + N_CHARGED or len(resale) < N_RESALE:
        raise RuntimeError("not enough free invoices for the use-tax pattern")

    # destination states are spread over the three states
    def dest_for(i, k):
        others = sorted(s for s in RATES if s != vendor_state[i["vendor_id"]])
        return others[k % len(others)]

    groups = [("use_tax_exposure", supply[:N_PLANTED]),
              ("cross_state_tax_charged", supply[N_PLANTED:N_PLANTED + N_CHARGED]),
              ("cross_state_resale_inventory", resale[:N_RESALE])]
    cross = {}
    for pat, rows in groups:
        for k, inv in enumerate(rows):
            cross[inv["invoice_id"]] = (pat, dest_for(inv, k + rng.randint(0, 1)))

    tag = {}
    for inv in t["invoices"]:
        iid = inv["invoice_id"]
        if iid in cross:
            pat, dest = cross[iid]
            inv["site_id"] = site_of_state[dest]
            if pat == "cross_state_tax_charged":
                inv["tax_amt"] = str(_tax_inside(base(inv), dest))
            else:
                inv["tax_amt"] = "0.00"
            tag[iid] = (pat, dest)
        else:
            state = state_of_site[inv["site_id"]]
            inv["tax_amt"] = str(_tax_inside(base(inv), state))

    for pat, rows in groups:
        kind, severity, expected = MANIFEST_TAX[pat]
        for inv in sorted(rows, key=lambda i: i["invoice_id"]):
            iid = inv["invoice_id"]
            refs = {"invoice_ids": [iid], "destination_state": tag[iid][1]}
            if pat == "use_tax_exposure":
                refs["expected_use_tax"] = str(_cents(base(inv) * RATES[tag[iid][1]]))
            ds.manifest.append({"kind": kind, "agent": "ap_guardian", "pattern": pat,
                                "severity": severity, "expected_behavior": expected,
                                "record_refs": refs})


def C_dec(x):
    return Decimal(str(x))
