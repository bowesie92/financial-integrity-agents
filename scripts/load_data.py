"""Load one generated seed into Supabase and verify it. Safe to re-run.

Usage: python scripts/load_data.py --seed 1 [--dir data/generated] [--force]

Replaces the synthetic data tables and the ground-truth manifest in one transaction, so a
failure leaves the previous data untouched. Refuses to run if findings exist (they point at
records that a reload would replace) unless --force is given.
"""
import argparse
import csv
import math
from pathlib import Path

import psycopg
from psycopg import sql

from setup_fia_roles import connect, load

# Load order follows foreign keys. (schema, table)
TABLES = [
    ("fia", "sites"), ("fia", "users"), ("fia", "accounts"), ("fia", "periods"),
    ("fia", "vendors"), ("fia", "journal_entries"), ("fia", "gl_lines"),
    ("fia", "purchase_orders"), ("fia", "invoices"), ("fia", "invoice_lines"),
    ("fia", "payments"), ("fia", "vendor_bank_changes"), ("fia_gt", "manifest"),
]
# Data tables replaced on every load. findings and finding_reviews are never touched.
TRUNCATE = ("fia.payments, fia.invoice_lines, fia.invoices, fia.purchase_orders, "
            "fia.vendor_bank_changes, fia.vendors, fia.gl_lines, fia.journal_entries, "
            "fia.periods, fia.accounts, fia.users, fia.sites, fia_gt.manifest")


def csv_info(path):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        return header, sum(1 for _ in reader)


def check_files(folder, seed):
    counts = {}
    for schema, table in TABLES:
        path = folder / f"{table}.csv"
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run: python -m generator --seed {seed}")
        counts[(schema, table)] = csv_info(path)
    with open(folder / "manifest.csv", newline="", encoding="utf-8") as f:
        seeds = {row["seed"] for row in csv.DictReader(f)}
    if seeds != {str(seed)}:
        raise SystemExit(f"{folder} holds seed(s) {sorted(seeds)}, not {seed}.")
    return counts


def replace_data(conn, folder, seed, counts):
    conn.execute("set statement_timeout = '5min'")
    conn.execute(sql.SQL("truncate {} restart identity").format(sql.SQL(TRUNCATE)))
    for schema, table in TABLES:
        header, _ = counts[(schema, table)]
        stmt = sql.SQL("copy {}.{} ({}) from stdin with (format csv, header true)").format(
            sql.Identifier(schema), sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(c) for c in header))
        with open(folder / f"{table}.csv", "rb") as f, conn.cursor().copy(stmt) as copy:
            while block := f.read(1 << 16):
                copy.write(block)
        print(f"  loaded {schema}.{table}")
    for schema, table in TABLES:
        conn.execute(sql.SQL("analyze {}.{}").format(sql.Identifier(schema), sql.Identifier(table)))


def first_digit_mad(rows):
    n = sum(c for _, c in rows)
    got = {d: c for d, c in rows}
    return sum(abs(got.get(d, 0) / n - math.log10(1 + 1 / d)) for d in range(1, 10)) / 9, n


def verify(admin, agent_connect, counts):
    bad = 0

    def report(ok, label):
        nonlocal bad
        bad += 0 if ok else 1
        print(("OK:      " if ok else "PROBLEM: ") + label)

    for (schema, table), (_, n) in counts.items():
        got = admin.execute(sql.SQL("select count(*) from {}.{}").format(
            sql.Identifier(schema), sql.Identifier(table))).fetchone()[0]
        report(got == n, f"{schema}.{table}: {got:,} rows (file has {n:,})")

    unbalanced = admin.execute(
        "select count(*) from (select je_id from fia.gl_lines group by je_id "
        "having sum(debit) <> sum(credit)) x").fetchone()[0]
    report(unbalanced == 0, f"every journal entry balances ({unbalanced} unbalanced)")
    short = admin.execute(
        "select count(*) from (select invoice_id from fia.invoice_lines group by invoice_id) l "
        "join fia.invoices i using (invoice_id) join (select invoice_id, sum(amount) s from "
        "fia.invoice_lines group by invoice_id) t using (invoice_id) where t.s <> i.total_amt"
    ).fetchone()[0]
    report(short == 0, f"invoice lines sum to invoice totals ({short} off)")

    rows = admin.execute(
        "select extract(quarter from je.entry_date)::int q, "
        "left(replace(greatest(gl.debit, gl.credit)::text, '.', ''), 1)::int d, count(*) "
        "from fia.gl_lines gl join fia.journal_entries je using (je_id) "
        "where greatest(gl.debit, gl.credit) >= 1 group by 1, 2").fetchall()
    by_q = {}
    for q, d, c in rows:
        by_q.setdefault(q, []).append((d, c))
    planted = admin.execute(
        "select record_refs->>'quarter' from fia_gt.manifest where pattern = 'benford_violation'"
    ).fetchone()[0]
    for q in sorted(by_q):
        mad, n = first_digit_mad(by_q[q])
        expect_bad = planted == f"2025-Q{q}"
        report((mad > 0.015) == expect_bad and (expect_bad or mad < 0.006) and n >= 5000,
               f"Q{q} first-digit MAD {mad:.4f} on {n:,} lines "
               f"({'planted violation' if expect_bad else 'clean'})")

    no_tax = admin.execute("select count(*) from fia.invoices where tax_amt is null").fetchone()[0]
    report(no_tax == 0, f"every invoice has tax_amt ({no_tax} missing)")
    detected = {r[0] for r in admin.execute(
        "select i.invoice_id from fia.invoices i join fia.vendors v using (vendor_id) "
        "join fia.sites s on s.site_id = i.site_id where v.state <> s.state and i.tax_amt = 0 "
        "and exists (select 1 from fia.invoice_lines l where l.invoice_id = i.invoice_id "
        "and l.account_id in ('6300','6310'))").fetchall()}
    planted_tax = {r[0] for r in admin.execute(
        "select jsonb_array_elements_text(record_refs->'invoice_ids') from fia_gt.manifest "
        "where pattern = 'use_tax_exposure'").fetchall()}
    report(detected == planted_tax and planted_tax,
           f"untaxed cross-state purchases of taxable goods match the manifest "
           f"({len(detected)} found, {len(planted_tax)} planted)")

    checks = [
        ("je_ids", "select count(*) from (select jsonb_array_elements_text(record_refs->'je_ids') "
                   "id from fia_gt.manifest where record_refs ? 'je_ids') m "
                   "where id not in (select je_id from fia.journal_entries)"),
        ("invoice_ids", "select count(*) from (select jsonb_array_elements_text(record_refs->"
                        "'invoice_ids') id from fia_gt.manifest where record_refs ? 'invoice_ids') m "
                        "where id not in (select invoice_id from fia.invoices)"),
        ("payment_ids", "select count(*) from (select jsonb_array_elements_text(record_refs->"
                        "'payment_ids') id from fia_gt.manifest where record_refs ? 'payment_ids') m "
                        "where id not in (select payment_id from fia.payments)"),
        ("po_id", "select count(*) from fia_gt.manifest where record_refs ? 'po_id' and "
                  "record_refs->>'po_id' not in (select po_id from fia.purchase_orders)"),
        ("vendor_id", "select count(*) from fia_gt.manifest where record_refs ? 'vendor_id' and "
                      "record_refs->>'vendor_id' not in (select vendor_id from fia.vendors)"),
    ]
    for label, query in checks:
        missing = admin.execute(query).fetchone()[0]
        report(missing == 0, f"manifest {label} all exist in the data ({missing} missing)")

    agent = agent_connect()
    n_inv = agent.execute("select count(*) from fia.invoices").fetchone()[0]
    report(n_inv == counts[("fia", "invoices")][1], "agent role can read the data")
    agent.execute("select tax_amt from fia.invoices limit 1")
    report(True, "agent role can read tax_amt")
    for label, stmt in [("agent role cannot read ground truth", "select 1 from fia_gt.manifest"),
                        ("agent role cannot write data",
                         "insert into fia.sites values (99, 'x', 'AZ', 'America/Phoenix')"),
                        ("agent role cannot read reviews", "select 1 from fia.finding_reviews")]:
        try:
            agent.execute(stmt)
            report(False, label)
        except psycopg.errors.InsufficientPrivilege:
            report(True, label)
    agent.close()
    return bad


def run(seed, folder, force, admin_connect, agent_connect):
    counts = check_files(folder, seed)
    conn = admin_connect()
    has_tax = conn.execute("select count(*) from information_schema.columns where "
                           "table_schema='fia' and table_name='invoices' and column_name='tax_amt'"
                           ).fetchone()[0]
    if not has_tax:
        raise SystemExit("fia.invoices has no tax_amt column. Apply db/002_use_tax.sql first: "
                         "python scripts/apply_migration.py db/002_use_tax.sql")
    conn.autocommit = False
    n_findings = conn.execute("select count(*) from fia.findings").fetchone()[0]
    if n_findings and not force:
        raise SystemExit(f"{n_findings} findings exist and a reload would orphan them. "
                         "Re-run with --force only if you accept that they will point at replaced data.")
    print(f"Replacing data with seed {seed} (one transaction)")
    try:
        replace_data(conn, folder, seed, counts)
        conn.commit()
    except Exception:
        conn.rollback()
        print("Load failed and was rolled back. The previous data is unchanged.")
        raise
    conn.autocommit = True
    bad = verify(conn, agent_connect, counts)
    conn.close()
    print(f"Seed {seed} loaded; all checks passed" if bad == 0 else f"{bad} check(s) failed")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--dir", default="data/generated")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    env = load()
    folder = Path(args.dir) / f"seed{args.seed}"
    run(args.seed, folder, args.force,
        lambda: connect(env, "fia_admin", env["SUPABASE_FIA_ADMIN_PASSWORD"]),
        lambda: connect(env, "fia_agent", env["SUPABASE_FIA_AGENT_PASSWORD"]))


if __name__ == "__main__":
    main()
