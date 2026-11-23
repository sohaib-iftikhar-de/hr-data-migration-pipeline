-- =====================================================================
-- RAW -> STAGING
-- Normalises three very different source formats into one shape.
-- Typed columns are NULL when a value can't be parsed; the original text
-- is kept in *_raw columns so the DQ report can show exactly what was wrong.
-- Exact duplicate rows (the same record extracted twice) are collapsed here.
-- =====================================================================

DROP TABLE IF EXISTS staging.worker;

CREATE TABLE staging.worker (
    source_system  text NOT NULL,
    source_id      text,
    first_name     text,
    last_name      text,
    gender         text,
    birth_date     date,
    birth_date_raw text,
    hire_date      date,
    hire_date_raw  text,
    end_date       date,            -- NULL = open-ended (still employed)
    end_date_raw   text,
    country_iso2   char(2),
    country_raw    text,
    status         text,
    status_raw     text,
    job_profile    text,
    job_code_raw   text,
    annual_salary  numeric(12,2),
    salary_raw     text,
    currency       text,
    email          text,
    source_file    text
);

-- ------------------------------------------------------------- EU (SAP-style)
INSERT INTO staging.worker
SELECT DISTINCT ON (r.pernr, r.vorna, r.nachn, r.gesch, r.gbdat, r.begda, r.endda,
                    r.land1, r.stat2, r.stell, r.ansal, r.waers, r.email)
    'EU',
    NULLIF(btrim(r.pernr), ''),
    util.clean_name(r.vorna),
    util.clean_name(r.nachn),
    CASE r.gesch WHEN '1' THEN 'Male' WHEN '2' THEN 'Female' ELSE 'Unknown' END,
    util.try_date(r.gbdat, 'DD.MM.YYYY'), r.gbdat,
    util.try_date(r.begda, 'DD.MM.YYYY'), r.begda,
    CASE WHEN r.endda = '31.12.9999' THEN NULL                  -- SAP "open-ended"
         ELSE util.try_date(r.endda, 'DD.MM.YYYY') END,
    CASE WHEN r.endda = '31.12.9999' THEN NULL ELSE r.endda END,
    c.iso2, r.land1,
    s.status, r.stat2,
    j.job_profile, r.stell,
    -- "48.000,00" -> 48000.00
    util.try_numeric(replace(replace(r.ansal, '.', ''), ',', '.')), r.ansal,
    upper(btrim(r.waers)),
    lower(btrim(r.email)),
    r._source_file
FROM raw.eu_sap_workers r
LEFT JOIN mapping.country       c ON c.source_code = btrim(r.land1)
LEFT JOIN mapping.worker_status s ON s.source_system = 'EU'   AND s.source_code = btrim(r.stat2)
LEFT JOIN mapping.job_profile   j ON j.source_system = 'EU'   AND j.source_code = btrim(r.stell);

-- ------------------------------------------------------------- NA (Oracle-style)
INSERT INTO staging.worker
SELECT DISTINCT ON (r.person_id, r.employee_number, r.first_name, r.last_name, r.sex,
                    r.date_of_birth, r.effective_start_date, r.effective_end_date,
                    r.country, r.assignment_status, r.job_code, r.salary, r.currency, r.email)
    'NA',
    NULLIF(btrim(r.person_id), ''),
    util.clean_name(r.first_name),
    util.clean_name(r.last_name),
    CASE upper(btrim(r.sex)) WHEN 'M' THEN 'Male' WHEN 'F' THEN 'Female' ELSE 'Unknown' END,
    util.try_date(r.date_of_birth, 'YYYY-MM-DD'), r.date_of_birth,
    util.try_date(r.effective_start_date, 'YYYY-MM-DD'), r.effective_start_date,
    CASE WHEN r.effective_end_date = '4712-12-31' THEN NULL    -- Oracle "end of time"
         ELSE util.try_date(r.effective_end_date, 'YYYY-MM-DD') END,
    CASE WHEN r.effective_end_date = '4712-12-31' THEN NULL ELSE r.effective_end_date END,
    c.iso2, r.country,
    s.status, r.assignment_status,
    j.job_profile, r.job_code,
    util.try_numeric(r.salary), r.salary,
    upper(btrim(r.currency)),
    lower(btrim(r.email)),
    r._source_file
FROM raw.na_oracle_workers r
LEFT JOIN mapping.country       c ON c.source_code = btrim(r.country)
LEFT JOIN mapping.worker_status s ON s.source_system = 'NA'   AND s.source_code = btrim(r.assignment_status)
LEFT JOIN mapping.job_profile   j ON j.source_system = 'NA'   AND j.source_code = btrim(r.job_code);

-- ------------------------------------------------------------- APAC (SuccessFactors-style)
INSERT INTO staging.worker
SELECT DISTINCT ON (r.personidexternal, r.userid, r.firstname, r.lastname, r.gender,
                    r.dateofbirth, r.startdate, r.enddate, r.country, r.emplstatus,
                    r.jobcode, r.salary, r.currency, r.email)
    'APAC',
    NULLIF(btrim(r.personidexternal), ''),
    util.clean_name(r.firstname),
    util.clean_name(r.lastname),
    CASE upper(btrim(r.gender)) WHEN 'M' THEN 'Male' WHEN 'F' THEN 'Female' ELSE 'Unknown' END,
    util.sf_date(r.dateofbirth), r.dateofbirth,
    util.sf_date(r.startdate),   r.startdate,
    CASE WHEN util.sf_date(r.enddate) = DATE '9999-12-31' THEN NULL
         ELSE util.sf_date(r.enddate) END,
    CASE WHEN util.sf_date(r.enddate) = DATE '9999-12-31' THEN NULL ELSE r.enddate END,
    c.iso2, r.country,
    s.status, r.emplstatus,
    j.job_profile, r.jobcode,
    util.try_numeric(r.salary), r.salary,
    upper(btrim(r.currency)),
    lower(btrim(r.email)),
    r._source_file
FROM raw.apac_sf_workers r
LEFT JOIN mapping.country       c ON c.source_code = btrim(r.country)
LEFT JOIN mapping.worker_status s ON s.source_system = 'APAC' AND s.source_code = btrim(r.emplstatus)
LEFT JOIN mapping.job_profile   j ON j.source_system = 'APAC' AND j.source_code = btrim(r.jobcode);

ANALYZE staging.worker;
