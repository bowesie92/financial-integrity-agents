"""Apply db/001_schema.sql, then verify the agent role's privileges. Safe to re-run."""
from pathlib import Path

from setup_fia_roles import connect, load

SQL_FILE = Path(__file__).resolve().parent.parent / "db" / "001_schema.sql"

CHECKS = [
    ("agent can read GL lines", "select has_table_privilege('fia_agent','fia.gl_lines','SELECT')", True),
    ("agent cannot write GL lines", "select has_table_privilege('fia_agent','fia.gl_lines','INSERT')", False),
    ("agent cannot write invoices", "select has_table_privilege('fia_agent','fia.invoices','UPDATE')", False),
    ("agent can insert findings", "select has_table_privilege('fia_agent','fia.findings','INSERT')", True),
    ("agent cannot update findings", "select has_table_privilege('fia_agent','fia.findings','UPDATE')", False),
    ("agent cannot delete findings", "select has_table_privilege('fia_agent','fia.findings','DELETE')", False),
    ("agent cannot read reviews", "select has_table_privilege('fia_agent','fia.finding_reviews','SELECT')", False),
    ("agent cannot see ground truth", "select has_schema_privilege('fia_agent','fia_gt','USAGE')", False),
]


def main():
    env = load()
    with connect(env, "postgres", env["SUPABASE_DB_PASSWORD"]) as conn:
        conn.execute("create schema if not exists fia_gt authorization fia_admin")
    with connect(env, "fia_admin", env["SUPABASE_FIA_ADMIN_PASSWORD"]) as conn:
        conn.execute(SQL_FILE.read_text())
        print("schema applied")
        bad = 0
        for label, query, want in CHECKS:
            got = conn.execute(query).fetchone()[0]
            ok = got == want
            bad += 0 if ok else 1
            print(("OK:      " if ok else "PROBLEM: ") + label)
        n = conn.execute(
            "select count(*) from information_schema.tables where table_schema in ('fia','fia_gt')"
        ).fetchone()[0]
        print("tables in fia and fia_gt:", n, "(expected 15)")
        print("all privilege checks passed" if bad == 0 else f"{bad} privilege check(s) failed")


if __name__ == "__main__":
    main()
