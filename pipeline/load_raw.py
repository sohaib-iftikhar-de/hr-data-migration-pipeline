"""Land source files in the RAW layer exactly as they are.

This is the Python equivalent of the NiFi ingestion flow (see nifi/README.md):
both write the same raw tables, so the rest of the pipeline doesn't care which
one ran. Values are loaded as text with no cleaning, via PostgreSQL COPY.
"""
import csv
import json
from pathlib import Path

SOURCES = {
    # file name               -> (raw table,               format, delimiter)
    "eu_sap_workers.csv":     ("raw.eu_sap_workers",     "csv",  ";"),
    "na_oracle_workers.csv":  ("raw.na_oracle_workers",  "csv",  ","),
    "apac_sf_workers.json":   ("raw.apac_sf_workers",    "json", None),
}


def read_records(path: Path, fmt: str, delimiter: str | None) -> tuple[list[str], list[list]]:
    """Return (lower-cased column names, rows) for a source file."""
    if fmt == "csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = [h.strip().lower() for h in next(reader)]
            return header, [row for row in reader]
    # SuccessFactors OData: {"d": {"results": [ {...}, ... ]}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload["d"]["results"]
    keys = list(records[0].keys())
    return [k.lower() for k in keys], [[r.get(k) for k in keys] for r in records]


def load_file(conn, path: Path) -> int:
    table, fmt, delimiter = SOURCES[path.name]
    columns, rows = read_records(path, fmt, delimiter)
    cols = ", ".join(columns + ["_source_file"])
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row([*row, path.name])
    return len(rows)


def load_all(conn, input_dir: Path) -> dict[str, int]:
    counts = {}
    for name in SOURCES:
        path = input_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing source file: {path}")
        counts[name] = load_file(conn, path)
    return counts
