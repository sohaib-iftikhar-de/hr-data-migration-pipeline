# Ingesting with Apache NiFi

The Python loader (`pipeline/load_raw.py`) and this NiFi flow do the same job:
land the three source files in the `raw` tables, untouched. Use NiFi to practise
the tool most enterprise migrations use for ingestion.

```
ListFile ─► FetchFile ─► RouteOnAttribute ─┬─► PutDatabaseRecord (EU CSV reader)   ─► raw.eu_sap_workers
                                           ├─► PutDatabaseRecord (NA CSV reader)   ─► raw.na_oracle_workers
                                           └─► PutDatabaseRecord (APAC JSON reader) ─► raw.apac_sf_workers
```

## 1. Prepare

```bash
# PostgreSQL JDBC driver (Windows 10+ ships curl)
curl -L -o nifi/drivers/postgresql-42.7.4.jar https://jdbc.postgresql.org/download/postgresql-42.7.4.jar

python -m generator.generate                 # source files in data/input
docker compose --profile nifi up -d          # PostgreSQL + NiFi
python -m pipeline.run --init-only           # create the empty raw tables
```

Open http://localhost:8080/nifi (allow 1–2 minutes for NiFi to start).

## 2. Controller services

Right-click the canvas → **Configure** → **Controller Services** → **+**

| Service | Property | Value |
|---|---|---|
| **DBCPConnectionPool** | Database Connection URL | `jdbc:postgresql://postgres:5432/hr_migration` |
| | Database Driver Class Name | `org.postgresql.Driver` |
| | Database Driver Location(s) | `/opt/nifi/drivers/postgresql-42.7.4.jar` |
| | Database User / Password | `postgres` / `postgres` |
| **CSVReader**, name it `EU CSV` | Schema Access Strategy | Use String Fields From Header |
| | Value Separator | `;` |
| | Treat First Line as Header | true |
| **CSVReader**, name it `NA CSV` | Schema Access Strategy | Use String Fields From Header |
| | Value Separator | `,` |
| | Treat First Line as Header | true |
| **JsonTreeReader**, name it `APAC JSON` | Schema Access Strategy | Infer Schema |
| | Starting Field Strategy | Nested Field |
| | Starting Field Name | `results` |

Enable all four (lightning-bolt icon).

## 3. Processors

| Processor | Key properties |
|---|---|
| **ListFile** | Input Directory: `/opt/nifi/input` |
| **FetchFile** | defaults |
| **RouteOnAttribute** | add 3 properties: `eu` = `${filename:equals('eu_sap_workers.csv')}`, `na` = `${filename:equals('na_oracle_workers.csv')}`, `apac` = `${filename:equals('apac_sf_workers.json')}` |
| **PutDatabaseRecord** ×3 | Record Reader: `EU CSV` / `NA CSV` / `APAC JSON` · Database Type: PostgreSQL · Statement Type: INSERT · Database Connection Pooling Service: the DBCP pool · Schema Name: `raw` · Table Name: `eu_sap_workers` / `na_oracle_workers` / `apac_sf_workers` · Translate Field Names: true · Unmatched Column Behavior: Ignore Unmatched Columns |

Connect them as in the diagram (`RouteOnAttribute` relationships `eu`, `na`, `apac`),
auto-terminate `unmatched` and `success`, and route `failure` to a funnel so you can
inspect bad flowfiles. Start the flow.

> `_source_file` stays empty when NiFi loads the data. To fill it, add an
> **UpdateRecord** before each PutDatabaseRecord with `/_source_file` = `${filename}`.

## 4. Run the rest of the pipeline

```bash
python -m pipeline.run --skip-load           # staging -> DQ -> curated -> report
```

The reconciliation numbers should match a Python-loaded run exactly.
