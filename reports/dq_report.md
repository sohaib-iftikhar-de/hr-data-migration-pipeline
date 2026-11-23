# Data Quality Report

_Generated 2026-11-23 21:49_

**9,045** raw records → **8,698** migration-ready (96.2%), **317** rejected, **30** exact duplicates collapsed, **170** migrated with warnings.

## Reconciliation

Every raw record is accounted for: `staging = curated + rejected`.

| Source | Raw | Duplicates collapsed | Staging | Curated | Rejected | With warnings | Balanced |
|---|---:|---:|---:|---:|---:|---:|:---:|
| EU | 3,030 | 30 | 3,000 | 2,897 | 103 | 0 | ✅ |
| NA | 3,015 | 0 | 3,015 | 2,900 | 115 | 38 | ✅ |
| APAC | 3,000 | 0 | 3,000 | 2,901 | 99 | 132 | ✅ |

## Rule failures

| Rule | Severity | EU | NA | APAC | Total |
|---|---|---:|---:|---:|---:|
| `missing_name` | error | 31 | 0 | 31 | 62 |
| `invalid_birth_date` | error | 28 | 0 | 27 | 55 |
| `unmapped_job_code` | error | 26 | 0 | 26 | 52 |
| `invalid_salary` | error | 0 | 34 | 0 | 34 |
| `implausible_birth_date` | error | 0 | 33 | 0 | 33 |
| `conflicting_duplicate_id` | error | 0 | 30 | 0 | 30 |
| `unmapped_status` | error | 0 | 18 | 0 | 18 |
| `end_before_hire` | error | 18 | 0 | 0 | 18 |
| `status_end_date_mismatch` | error | 16 | 0 | 0 | 16 |
| `unmapped_country` | error | 0 | 0 | 15 | 15 |
| `gender_unknown` | warning | 0 | 0 | 140 | 140 |
| `invalid_email` | warning | 0 | 38 | 0 | 38 |

## One example per rule

| Rule | Record | Detail |
|---|---|---|
| `conflicting_duplicate_id` | NA-200127 | ID appears 2 times with different values |
| `end_before_hire` | EU-10000412 | hire_date=2024-10-10, end_date=2024-09-10 |
| `gender_unknown` | APAC-300027 | gender not provided by source |
| `implausible_birth_date` | NA-200099 | birth_date=2031-05-04 (age must be 16-100) |
| `invalid_birth_date` | APAC-300185 | raw value: <blank> |
| `invalid_email` | NA-200033 | email: not-an-email |
| `invalid_salary` | NA-200054 | raw value: N/A |
| `missing_name` | APAC-300153 | first_name=<null>, last_name=Miller |
| `status_end_date_mismatch` | EU-10000412 | status=Active, end_date=2024-09-10 |
| `unmapped_country` | APAC-300733 | country: XXX |
| `unmapped_job_code` | APAC-300010 | job code: J-999 |
| `unmapped_status` | NA-200019 | status: SUSP_ASSIGN |

Full list of rejected records: `rejected_records.csv`.
