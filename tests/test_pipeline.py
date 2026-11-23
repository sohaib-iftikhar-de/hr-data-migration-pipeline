"""End-to-end and rule-level tests.

Generates a fresh small dataset, runs the whole pipeline once, then checks the
result. Needs a PostgreSQL database (docker compose up -d postgres).
"""
from datetime import date

import pytest

from generator.generate import main as generate
from pipeline.db import connect
from pipeline.report import reconcile
from pipeline.run import main as run_pipeline


@pytest.fixture(scope="session")
def conn(tmp_path_factory):
    data = tmp_path_factory.mktemp("input")
    reports = tmp_path_factory.mktemp("reports")
    import sys
    argv = sys.argv
    sys.argv = ["generate", "--workers", "600", "--out", str(data), "--seed", "7"]
    try:
        generate()
    finally:
        sys.argv = argv
    assert run_pipeline(["--input", str(data), "--reports", str(reports)]) == 0
    with connect() as c:
        yield c


def scalar(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]


# ---------------------------------------------------------------- reconciliation

def test_every_record_is_accounted_for(conn):
    for r in reconcile(conn):
        assert r["balanced"], r
        assert r["raw"] == r["duplicates_collapsed"] + r["curated"] + r["rejected"]


def test_exact_duplicates_are_collapsed_not_rejected(conn):
    eu = next(r for r in reconcile(conn) if r["source_system"] == "EU")
    assert eu["duplicates_collapsed"] > 0
    assert scalar(conn, "SELECT count(*) FROM dq.rule_failure "
                        "WHERE source_system = 'EU' AND rule = 'conflicting_duplicate_id'") == 0


def test_conflicting_duplicates_never_reach_curated(conn):
    clashing = conn.execute("""
        SELECT DISTINCT source_id FROM dq.rule_failure
        WHERE rule = 'conflicting_duplicate_id'
    """).fetchall()
    assert clashing, "generator should produce conflicting duplicates"
    for (sid,) in clashing:
        assert scalar(conn, "SELECT count(*) FROM curated.worker WHERE source_id = %s", sid) == 0


# ---------------------------------------------------------------- curated contract

def test_curated_has_no_missing_required_fields(conn):
    assert scalar(conn, """
        SELECT count(*) FROM curated.worker
        WHERE first_name IS NULL OR last_name IS NULL OR birth_date IS NULL
           OR hire_date IS NULL OR country_iso2 IS NULL OR status IS NULL
           OR job_profile IS NULL OR annual_salary IS NULL
    """) == 0


def test_open_ended_dates_become_null(conn):
    # 31.12.9999 (SAP), 4712-12-31 (Oracle) and /Date(253402214400000)/ (SF) must not survive
    assert scalar(conn, "SELECT count(*) FROM curated.worker WHERE end_date >= DATE '4712-01-01'") == 0
    assert scalar(conn, "SELECT count(*) FROM curated.worker WHERE status = 'Active' AND end_date IS NULL") > 0


def test_terminated_workers_have_end_dates(conn):
    assert scalar(conn, "SELECT count(*) FROM curated.worker "
                        "WHERE status = 'Terminated' AND end_date IS NULL") == 0


def test_names_are_trimmed_and_title_cased(conn):
    assert scalar(conn, """
        SELECT count(*) FROM curated.worker
        WHERE first_name <> btrim(first_name) OR first_name <> initcap(first_name)
    """) == 0


def test_country_codes_are_iso2(conn):
    codes = {r[0] for r in conn.execute("SELECT DISTINCT country_iso2 FROM curated.worker")}
    assert codes <= {"DE", "NO", "CH", "US", "CA", "AU", "SG", "JP"}
    assert {"AU", "SG", "JP"} & codes, "ISO-3 APAC codes should be mapped to ISO-2"


def test_european_salary_format_is_parsed(conn):
    # "102.516,00" -> 102516.00
    row = conn.execute("""
        SELECT r.ansal, c.annual_salary
        FROM raw.eu_sap_workers r JOIN curated.worker c
          ON c.source_system = 'EU' AND c.source_id = r.pernr
        LIMIT 1
    """).fetchone()
    expected = float(row[0].replace(".", "").replace(",", "."))
    assert float(row[1]) == expected


# ---------------------------------------------------------------- each defect is caught

@pytest.mark.parametrize("rule, system", [
    ("invalid_birth_date",       "EU"),    # 31.02.1988
    ("missing_name",             "EU"),
    ("unmapped_job_code",        "EU"),
    ("end_before_hire",          "EU"),
    ("implausible_birth_date",   "NA"),    # born in the future
    ("invalid_salary",           "NA"),    # "N/A"
    ("unmapped_status",          "NA"),
    ("conflicting_duplicate_id", "NA"),
    ("missing_name",             "APAC"),  # null firstName
    ("invalid_birth_date",       "APAC"),  # blank dateOfBirth
    ("unmapped_country",         "APAC"),  # "XXX"
])
def test_injected_defects_are_rejected(conn, rule, system):
    failing = scalar(conn, "SELECT count(*) FROM dq.rule_failure "
                           "WHERE rule = %s AND source_system = %s", rule, system)
    assert failing > 0, f"expected some {rule} failures in {system}"
    leaked = scalar(conn, """
        SELECT count(*) FROM curated.worker c
        JOIN dq.rule_failure f USING (source_system, source_id)
        WHERE f.rule = %s AND f.source_system = %s
    """, rule, system)
    assert leaked == 0


def test_warnings_are_migrated_but_flagged(conn):
    flagged = scalar(conn, "SELECT count(*) FROM curated.worker "
                           "WHERE 'invalid_email' = ANY(dq_warnings)")
    assert flagged > 0


# ---------------------------------------------------------------- parsing helpers

@pytest.mark.parametrize("value, fmt, expected", [
    ("15.06.1990", "DD.MM.YYYY", date(1990, 6, 15)),
    ("31.02.1988", "DD.MM.YYYY", None),        # impossible day
    ("1990-06-15", "YYYY-MM-DD", date(1990, 6, 15)),
    ("1990-13-01", "YYYY-MM-DD", None),        # impossible month
    ("", "YYYY-MM-DD", None),
    (None, "YYYY-MM-DD", None),
])
def test_try_date(conn, value, fmt, expected):
    assert scalar(conn, "SELECT util.try_date(%s, %s)", value, fmt) == expected


@pytest.mark.parametrize("value, expected", [
    ("/Date(642729600000)/", date(1990, 5, 15)),
    ("/Date(253402214400000)/", date(9999, 12, 31)),
    ("", None),
    (None, None),
    ("garbage", None),
])
def test_successfactors_date(conn, value, expected):
    assert scalar(conn, "SELECT util.sf_date(%s)", value) == expected


def test_pipeline_is_rerunnable(conn, tmp_path):
    before = scalar(conn, "SELECT count(*) FROM curated.worker")
    assert run_pipeline(["--skip-load", "--reports", str(tmp_path)]) == 0
    assert scalar(conn, "SELECT count(*) FROM curated.worker") == before
