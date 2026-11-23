"""Run the migration pipeline end to end.

    RAW (land files) -> STAGING (normalise) -> DQ (rules) -> CURATED (promote) -> report

Usage:
    python -m pipeline.run                       # load data/input and run everything
    python -m pipeline.run --skip-load           # raw tables already loaded by NiFi
    python -m pipeline.run --input data/input --reports reports
"""
import argparse
import sys
import time
from pathlib import Path

from pipeline.db import connect
from pipeline.load_raw import load_all
from pipeline.report import reconcile, write_report

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def run_sql(conn, name: str) -> None:
    conn.execute((SQL_DIR / name).read_text(encoding="utf-8"))


def step(label: str):
    print(f"  {label:<38}", end="", flush=True)
    return time.perf_counter()


def done(t0: float, extra: str = "") -> None:
    print(f"{time.perf_counter() - t0:6.2f}s  {extra}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/input", type=Path)
    p.add_argument("--reports", default="reports", type=Path)
    p.add_argument("--skip-load", action="store_true", help="raw tables were loaded by NiFi")
    p.add_argument("--init-only", action="store_true",
                   help="only create empty schemas and mappings (run before the NiFi flow)")
    a = p.parse_args(argv)

    print("HR migration pipeline")
    with connect() as conn:
        if not a.skip_load:
            t = step("1. create schemas + mappings")
            run_sql(conn, "01_schema.sql")
            run_sql(conn, "02_mapping.sql")
            done(t)
            if a.init_only:
                print("\nEmpty RAW tables are ready. Run the NiFi flow, then: python -m pipeline.run --skip-load")
                return 0

            t = step("2. land source files in RAW")
            counts = load_all(conn, a.input)
            done(t, ", ".join(f"{k}: {v:,}" for k, v in counts.items()))

        t = step("3. RAW -> STAGING (normalise)")
        run_sql(conn, "03_staging.sql")
        done(t)

        t = step("4. data-quality rules")
        run_sql(conn, "04_data_quality.sql")
        n = conn.execute("SELECT count(*) FROM dq.rule_failure").fetchone()[0]
        done(t, f"{n:,} rule failures")

        t = step("5. STAGING -> CURATED (promote)")
        run_sql(conn, "05_curated.sql")
        done(t)

        t = step("6. reconcile + report")
        recon = reconcile(conn)
        path = write_report(conn, recon, a.reports)
        done(t, str(path))

    print()
    print(f"  {'source':<6} {'raw':>7} {'dupes':>6} {'curated':>8} {'rejected':>9}  balanced")
    for r in recon:
        print(f"  {r['source_system']:<6} {r['raw']:>7,} {r['duplicates_collapsed']:>6,} "
              f"{r['curated']:>8,} {r['rejected']:>9,}  {'yes' if r['balanced'] else 'NO'}")

    if not all(r["balanced"] for r in recon):
        print("\nReconciliation FAILED: some records are unaccounted for.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
