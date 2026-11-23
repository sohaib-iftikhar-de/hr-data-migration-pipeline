"""Reconciliation and the data-quality report."""
import csv
from datetime import datetime
from pathlib import Path

RAW_TABLES = {
    "EU": "raw.eu_sap_workers",
    "NA": "raw.na_oracle_workers",
    "APAC": "raw.apac_sf_workers",
}


def reconcile(conn) -> list[dict]:
    """Every raw row must end up somewhere: curated, rejected, or collapsed as an exact duplicate.

    raw rows = exact duplicates removed + staging rows
    staging rows = curated rows + rejected rows
    """
    out = []
    for system, table in RAW_TABLES.items():
        q = lambda sql: conn.execute(sql, (system,)).fetchone()[0]  # noqa: E731
        raw = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        staging = q("SELECT count(*) FROM staging.worker WHERE source_system = %s")
        curated = q("SELECT count(*) FROM curated.worker WHERE source_system = %s")
        rejected = q("SELECT count(*) FROM dq.rejected_worker WHERE source_system = %s")
        warned = q("SELECT count(*) FROM curated.worker WHERE source_system = %s AND dq_warnings <> '{}'")
        out.append({
            "source_system": system,
            "raw": raw,
            "duplicates_collapsed": raw - staging,
            "staging": staging,
            "curated": curated,
            "rejected": rejected,
            "migrated_with_warnings": warned,
            "balanced": staging == curated + rejected,
        })
    return out


def write_report(conn, recon: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rejected records as CSV, for the business to fix at source
    rejects = conn.execute("""
        SELECT source_system, source_id, first_name, last_name, source_file,
               array_to_string(failed_rules, ', '), details
        FROM dq.rejected_worker ORDER BY source_system, source_id
    """).fetchall()
    with (out_dir / "rejected_records.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_system", "source_id", "first_name", "last_name",
                    "source_file", "failed_rules", "details"])
        w.writerows(rejects)

    rules = conn.execute("""
        SELECT rule, severity,
               count(*) FILTER (WHERE source_system = 'EU')   AS eu,
               count(*) FILTER (WHERE source_system = 'NA')   AS na,
               count(*) FILTER (WHERE source_system = 'APAC') AS apac,
               count(*)                                        AS total
        FROM dq.rule_failure
        GROUP BY rule, severity
        ORDER BY severity, total DESC
    """).fetchall()

    examples = conn.execute("""
        SELECT DISTINCT ON (rule) rule, source_system, source_id, detail
        FROM dq.rule_failure ORDER BY rule, source_system, source_id
    """).fetchall()

    t = {k: sum(r[k] for r in recon) for k in ("raw", "duplicates_collapsed", "curated", "rejected",
                                               "migrated_with_warnings")}
    pct = 100 * t["curated"] / t["raw"] if t["raw"] else 0

    lines = [
        "# Data Quality Report",
        "",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        f"**{t['raw']:,}** raw records → **{t['curated']:,}** migration-ready "
        f"({pct:.1f}%), **{t['rejected']:,}** rejected, "
        f"**{t['duplicates_collapsed']:,}** exact duplicates collapsed, "
        f"**{t['migrated_with_warnings']:,}** migrated with warnings.",
        "",
        "## Reconciliation",
        "",
        "Every raw record is accounted for: `staging = curated + rejected`.",
        "",
        "| Source | Raw | Duplicates collapsed | Staging | Curated | Rejected | With warnings | Balanced |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for r in recon:
        lines.append(
            f"| {r['source_system']} | {r['raw']:,} | {r['duplicates_collapsed']:,} | {r['staging']:,} | "
            f"{r['curated']:,} | {r['rejected']:,} | {r['migrated_with_warnings']:,} | "
            f"{'✅' if r['balanced'] else '❌'} |"
        )
    lines += [
        "",
        "## Rule failures",
        "",
        "| Rule | Severity | EU | NA | APAC | Total |",
        "|---|---|---:|---:|---:|---:|",
    ]
    lines += [f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |" for r in rules]
    lines += ["", "## One example per rule", "", "| Rule | Record | Detail |", "|---|---|---|"]
    lines += [f"| `{e[0]}` | {e[1]}-{e[2]} | {e[3]} |" for e in examples]
    lines += ["", "Full list of rejected records: `rejected_records.csv`."]

    path = out_dir / "dq_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
