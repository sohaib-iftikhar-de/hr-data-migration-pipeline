"""Generate messy, realistic HR extracts from three fictional regional systems.

Each region mimics the quirks of a different kind of legacy HR system:

  EU   (SAP-style)            semicolon CSV, DD.MM.YYYY dates, 31.12.9999 = open-ended,
                              gender as 1/2, salary with European decimals "4.250,00"
  NA   (Oracle HRMS-style)    comma CSV, ISO dates, 4712-12-31 = open-ended,
                              assignment status codes, padded/odd-cased names
  APAC (SuccessFactors-style) JSON, /Date(epoch_ms)/ dates, ISO-3 country codes,
                              salary as strings, nulls and blanks

A small share of records is deliberately broken (impossible dates, missing names,
unknown job codes, conflicting duplicate IDs, ...) so the data-quality layer has
something real to catch. Everything is seeded, so output is reproducible.

Usage:
    python -m generator.generate --workers 3000 --out data/input
"""
import argparse
import csv
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

FIRST = ["Anna", "Lukas", "Sofia", "Jonas", "Emma", "Noah", "Mia", "Elias", "Lea", "Ben",
         "Olivia", "Liam", "Ava", "Ethan", "Chloe", "Mason", "Aisha", "Omar", "Mei", "Hiro",
         "Priya", "Arjun", "Sakura", "Wei", "Chen", "Isla", "Jack", "Ruby", "Leo", "Zara"]
LAST = ["Muller", "Schmidt", "Hansen", "Berg", "Fischer", "Weber", "Smith", "Johnson",
        "Brown", "Garcia", "Miller", "Davis", "Tan", "Lim", "Wong", "Nguyen", "Kumar",
        "Singh", "Sato", "Tanaka", "Khan", "Ali", "Taylor", "Wilson", "Clark", "Walker"]

EU_JOBS = ["50000101", "50000102", "50000201", "50000301", "50000302"]
NA_JOBS = ["ENG.SR", "ENG.JR", "FIN.ANL", "HR.BP", "OPS.MGR"]
APAC_JOBS = ["J-101", "J-102", "J-201", "J-301", "J-302"]

OPEN_END = date(9999, 12, 31)


def rand_date(rng, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def person(rng):
    first, last = rng.choice(FIRST), rng.choice(LAST)
    birth = rand_date(rng, date(1960, 1, 1), date(2002, 12, 31))
    hire = rand_date(rng, date(2005, 1, 1), date(2025, 6, 30))
    terminated = rng.random() < 0.15
    end = rand_date(rng, hire + timedelta(days=60), date(2026, 6, 30)) if terminated else OPEN_END
    return first, last, birth, hire, end, terminated


def email(first, last, n, domain):
    return f"{first}.{last}{n}@{domain}".lower()


# ------------------------------------------------------------------ EU / SAP-style

def eu_salary(v: float) -> str:
    """4250.0 -> '4.250,00' (European formatting)."""
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def gen_eu(rng, n):
    rows = []
    for i in range(n):
        first, last, birth, hire, end, term = person(rng)
        pernr = f"{10000000 + i}"
        row = {
            "PERNR": pernr,
            "VORNA": first,
            "NACHN": last,
            "GESCH": rng.choice(["1", "2"]),
            "GBDAT": birth.strftime("%d.%m.%Y"),
            "BEGDA": hire.strftime("%d.%m.%Y"),
            "ENDDA": end.strftime("%d.%m.%Y"),
            "LAND1": rng.choice(["DE", "NO", "CH"]),
            "STAT2": "0" if term else "3",
            "STELL": rng.choice(EU_JOBS),
            "ANSAL": eu_salary(rng.randint(3000, 9000) * 12),
            "WAERS": "EUR",
            "EMAIL": email(first, last, i, "eu.example.com"),
        }
        r = rng.random()
        if r < 0.010: row["GBDAT"] = "31.02.1988"                 # impossible date
        elif r < 0.020: row["NACHN"] = ""                          # missing last name
        elif r < 0.030: row["STELL"] = "59999999"                  # unknown job code
        elif r < 0.035: row["ENDDA"] = (hire - timedelta(days=30)).strftime("%d.%m.%Y")  # ends before start
        rows.append(row)
    # exact duplicate re-extracts (same row twice) - should be collapsed, not rejected
    rows += [dict(r) for r in rng.sample(rows, max(1, n // 100))]
    return rows


# ------------------------------------------------------------------ NA / Oracle-style

def gen_na(rng, n):
    rows = []
    for i in range(n):
        first, last, birth, hire, end, term = person(rng)
        row = {
            "PERSON_ID": str(200000 + i),
            "EMPLOYEE_NUMBER": f"E{50000 + i}",
            "FIRST_NAME": f"  {first.upper()} " if rng.random() < 0.2 else first,   # padding / caps
            "LAST_NAME": last,
            "SEX": rng.choice(["M", "F"]),
            "DATE_OF_BIRTH": birth.isoformat(),
            "EFFECTIVE_START_DATE": hire.isoformat(),
            "EFFECTIVE_END_DATE": "4712-12-31" if not term else end.isoformat(),  # Oracle 'end of time'
            "COUNTRY": rng.choice(["US", "CA"]),
            "ASSIGNMENT_STATUS": "TERM_ASSIGN" if term else "ACTIVE_ASSIGN",
            "JOB_CODE": rng.choice(NA_JOBS),
            "SALARY": f"{rng.randint(50, 180) * 1000}",
            "CURRENCY": "USD" if rng.random() < 0.7 else "CAD",
            "EMAIL": email(first, last, i, "na.example.com"),
        }
        r = rng.random()
        if r < 0.010: row["EMAIL"] = "not-an-email"                       # invalid format
        elif r < 0.020: row["DATE_OF_BIRTH"] = "2031-05-04"               # birth date in the future
        elif r < 0.030: row["SALARY"] = "N/A"                             # non-numeric salary
        elif r < 0.035: row["ASSIGNMENT_STATUS"] = "SUSP_ASSIGN"          # unmapped status
        rows.append(row)
    # conflicting duplicates: same PERSON_ID, different data -> both must be rejected
    for src in rng.sample(rows, max(1, n // 200)):
        clash = dict(src)
        clash["JOB_CODE"] = "OPS.MGR" if src["JOB_CODE"] != "OPS.MGR" else "ENG.JR"
        clash["SALARY"] = str(int(src["SALARY"]) + 5000) if src["SALARY"].isdigit() else "90000"
        rows.append(clash)
    rng.shuffle(rows)
    return rows


# ------------------------------------------------------------------ APAC / SuccessFactors-style

def sf_date(d: date | None):
    if d is None:
        return None
    ms = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)
    return f"/Date({ms})/"


def gen_apac(rng, n):
    rows = []
    for i in range(n):
        first, last, birth, hire, end, term = person(rng)
        row = {
            "userId": f"sfu{300000 + i}",
            "personIdExternal": str(300000 + i),
            "firstName": first,
            "lastName": last,
            "gender": rng.choices(["M", "F", "U"], weights=[48, 48, 4])[0],
            "dateOfBirth": sf_date(birth),
            "startDate": sf_date(hire),
            "endDate": sf_date(end) if term else rng.choice([None, sf_date(OPEN_END)]),
            "country": rng.choice(["AUS", "SGP", "JPN"]),
            "emplStatus": "T" if term else "A",
            "jobCode": rng.choice(APAC_JOBS),
            "salary": str(rng.randint(60, 200) * 1000),
            "email": email(first, last, i, "apac.example.com"),
        }
        row["currency"] = {"AUS": "AUD", "SGP": "SGD", "JPN": "JPY"}[row["country"]]
        r = rng.random()
        if r < 0.010: row["firstName"] = None                     # null name
        elif r < 0.020: row["dateOfBirth"] = ""                   # blank date
        elif r < 0.030: row["jobCode"] = "J-999"                  # unknown job code
        elif r < 0.035: row["country"] = "XXX"                    # unknown country
        rows.append(row)
    return rows


# ------------------------------------------------------------------ writers

def write_csv(path: Path, rows: list[dict], delimiter: str):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=delimiter)
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workers", type=int, default=3000, help="workers per region")
    p.add_argument("--out", default="data/input")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()

    rng = random.Random(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    eu, na, apac = gen_eu(rng, a.workers), gen_na(rng, a.workers), gen_apac(rng, a.workers)
    write_csv(out / "eu_sap_workers.csv", eu, ";")
    write_csv(out / "na_oracle_workers.csv", na, ",")
    (out / "apac_sf_workers.json").write_text(json.dumps({"d": {"results": apac}}, indent=1))

    print(f"Wrote {len(eu):,} EU, {len(na):,} NA, {len(apac):,} APAC rows to {out}/")


if __name__ == "__main__":
    main()
