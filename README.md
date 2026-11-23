# Multi-Region HR Data Migration Pipeline

![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Apache NiFi](https://img.shields.io/badge/Apache%20NiFi-1.28-728E9B?logo=apachenifi&logoColor=white)

Consolidating workforce data from **three regional legacy HR systems**, each with its own formats and
quirks, into one clean, migration-ready worker dataset. Bad records are caught by automated
data-quality rules, explained, and sent back instead of being loaded. **Every source record is
accounted for.**

This is the core problem of any HRIS migration (e.g. to Workday): the target system is strict,
the sources are messy, and nobody can afford to lose or silently corrupt an employee record.

## Results (9,045 source records)

| Source | Raw | Duplicates collapsed | Curated | Rejected | Migrated with warnings | Balanced |
|---|---:|---:|---:|---:|---:|:---:|
| EU (SAP-style) | 3,030 | 30 | 2,897 | 103 | 0 | ✅ |
| NA (Oracle HRMS-style) | 3,015 | 0 | 2,900 | 115 | 38 | ✅ |
| APAC (SuccessFactors-style) | 3,000 | 0 | 2,901 | 99 | 132 | ✅ |
| **Total** | **9,045** | **30** | **8,698 (96.2%)** | **317** | **170** | ✅ |

Full output: [`reports/dq_report.md`](reports/dq_report.md) and
[`reports/rejected_records.csv`](reports/rejected_records.csv), one row per rejected worker
with every rule it failed.

## Architecture

```
  data/input/                     PostgreSQL
 ┌──────────────────────┐   ┌───────────────────────────────────────────────────────────────┐
 │ eu_sap_workers.csv   │   │  raw.*            staging.worker      dq.rule_failure          │
 │ na_oracle_workers.csv├──►│  (text, as-is) ──► (one shape,    ──► (15 rules,             │
 │ apac_sf_workers.json │   │                     typed)              error / warning)       │
 └──────────────────────┘   │                         │                    │                  │
   Python COPY loader       │                         ▼                    ▼                  │
   or Apache NiFi flow      │                  curated.worker      dq.rejected_worker        │
                            │                  (migration-ready)   (sent back to business)   │
                            └───────────────────────────────────────────────────────────────┘
                                     mapping.* lookup tables drive code translation
```

| Layer | What happens | Why |
|---|---|---|
| **raw** | Files land exactly as received, every column as text, plus source file and load time | Full traceability; any output row can be traced to the source file |
| **mapping** | Source codes → target values (job profiles, ISO countries, statuses) as **data** | New code = one-row insert, not a code change |
| **staging** | Three formats normalised into one typed shape; original values kept in `*_raw` columns | The DQ report can show *exactly* what was wrong |
| **dq** | 14 SQL rules record every failure with severity and detail | Errors block a record; warnings flag it |
| **curated** | Only error-free records promoted; warnings travel with the record | Clean input for the target load |

## The messy data it handles

| Source | Quirk | How it's handled |
|---|---|---|
| EU (SAP) | `DD.MM.YYYY` dates, impossible dates like `31.02.1988` | Safe parser returns NULL → `invalid_birth_date` |
| EU (SAP) | `31.12.9999` means "no end date" | Converted to NULL (still employed) |
| EU (SAP) | Salary as `102.516,00` (European decimals) | Parsed to `102516.00` |
| EU (SAP) | Gender as `1` / `2` | Mapped to Male / Female |
| EU (SAP) | Same record extracted twice | Exact duplicates collapsed, counted in reconciliation |
| NA (Oracle) | `4712-12-31` "end of time" | Converted to NULL |
| NA (Oracle) | `"  ANNA "` padded / upper-case names | Trimmed and title-cased |
| NA (Oracle) | Same `PERSON_ID` with *different* data | Both rejected: `conflicting_duplicate_id` (never guess) |
| NA (Oracle) | Salary `"N/A"`, birth dates in the future, unknown status codes | Rejected with the raw value in the report |
| APAC (SF) | `/Date(1234567890000)/` epoch-millisecond dates | Parsed with `util.sf_date()` |
| APAC (SF) | ISO-3 country codes (`AUS`, `SGP`) | Mapped to ISO-2 |
| APAC (SF) | `null` names, blank dates, unknown job codes | Rejected with reasons |

## Data-quality rules

| Rule | Severity | Catches |
|---|---|---|
| `missing_source_id` | error | Record without an ID |
| `conflicting_duplicate_id` | error | Same ID, different data |
| `missing_name` | error | Null or blank first/last name |
| `invalid_birth_date` / `invalid_hire_date` / `invalid_end_date` | error | Unparseable or blank dates |
| `implausible_birth_date` | error | Age outside 16–100 |
| `end_before_hire` | error | End date before hire date |
| `status_end_date_mismatch` | error | Terminated with no end date, or active with a past end date |
| `unmapped_job_code` / `unmapped_country` / `unmapped_status` | error | Code missing from the mapping tables |
| `invalid_salary` | error | Non-numeric or non-positive salary |
| `invalid_email` | warning | Malformed email (migrated, flagged) |
| `gender_unknown` | warning | Source didn't provide gender (migrated, flagged) |

Adding a rule is one `INSERT … SELECT` in [`sql/04_data_quality.sql`](sql/04_data_quality.sql);
the report and rejection logic pick it up automatically.

## Run it

Requires Docker and Python 3.10+.

```bash
pip install -r requirements.txt
docker compose up -d --wait            # PostgreSQL 16 on localhost:5432

python -m generator.generate           # (optional) regenerate the source extracts
python -m pipeline.run                 # raw -> staging -> DQ -> curated -> report
pytest -q                              # 33 tests
```

Output:

```
  source     raw  dupes  curated  rejected  balanced
  EU       3,030     30    2,897       103  yes
  NA       3,015      0    2,900       115  yes
  APAC     3,000      0    2,901        99  yes
```

The run fails with a non-zero exit code if any record is unaccounted for.

### Ingest with Apache NiFi instead

`docker compose --profile nifi up -d` starts NiFi alongside PostgreSQL. The step-by-step flow
(ListFile → FetchFile → RouteOnAttribute → PutDatabaseRecord ×3) is in
[`nifi/README.md`](nifi/README.md). NiFi writes the same `raw` tables, then
`python -m pipeline.run --skip-load` runs the rest.

## Tests

`pytest` generates a fresh dataset, runs the whole pipeline and checks:

- **Reconciliation**: `raw = duplicates + curated + rejected` for every source
- **Curated contract**: no missing required fields, ISO-2 countries only, no `9999`/`4712` sentinel dates
- **Every injected defect is caught**, and none leak into curated
- Conflicting duplicates never reach curated; exact duplicates are collapsed, not rejected
- Parsing helpers: impossible dates, European decimals, SuccessFactors dates
- The pipeline can be re-run safely

## Project layout

```
generator/generate.py       seeded synthetic extracts with realistic defects
sql/01_schema.sql           raw / staging / dq / curated schemas + safe parsers
sql/02_mapping.sql          job, country and status lookup tables
sql/03_staging.sql          per-source normalisation into one shape
sql/04_data_quality.sql     the 15 rules
sql/05_curated.sql          promote clean records, collect rejects
pipeline/load_raw.py        COPY-based raw loader (CSV + OData JSON)
pipeline/run.py             orchestrates the steps, exits non-zero on imbalance
pipeline/report.py          reconciliation + markdown/CSV report
nifi/README.md              NiFi ingestion flow
tests/test_pipeline.py      33 tests
```

All data is synthetic; names, IDs and companies are fictional.

## License

MIT
