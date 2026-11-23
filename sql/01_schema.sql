-- =====================================================================
-- Layered schemas for the HR migration
--
--   raw       exactly what the source sent: every column is text, nothing is
--             cleaned, plus load metadata. Never edited, so any record can be
--             traced back to the file it came from.
--   mapping   lookup tables: source codes -> target values
--   staging   one common shape for all regions, with typed values
--   dq        data-quality rule failures and run statistics
--   curated   clean, migration-ready workers (the "load to target" layer)
--   util      safe parsing helpers
-- =====================================================================

DROP SCHEMA IF EXISTS curated, dq, staging, mapping, raw, util CASCADE;
CREATE SCHEMA raw;
CREATE SCHEMA mapping;
CREATE SCHEMA staging;
CREATE SCHEMA dq;
CREATE SCHEMA curated;
CREATE SCHEMA util;

-- ------------------------------------------------------------- raw layer
-- Column names are the source field names in lower case, so NiFi's
-- PutDatabaseRecord can map fields to columns automatically.

CREATE TABLE raw.eu_sap_workers (
    pernr text, vorna text, nachn text, gesch text, gbdat text, begda text, endda text,
    land1 text, stat2 text, stell text, ansal text, waers text, email text,
    _source_file text,
    _loaded_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.na_oracle_workers (
    person_id text, employee_number text, first_name text, last_name text, sex text,
    date_of_birth text, effective_start_date text, effective_end_date text, country text,
    assignment_status text, job_code text, salary text, currency text, email text,
    _source_file text,
    _loaded_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.apac_sf_workers (
    userid text, personidexternal text, firstname text, lastname text, gender text,
    dateofbirth text, startdate text, enddate text, country text, emplstatus text,
    jobcode text, salary text, currency text, email text,
    _source_file text,
    _loaded_at   timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------- safe parsers
-- Legacy data contains impossible dates (31.02.1988) and junk numbers ("N/A").
-- These return NULL instead of failing the whole load; the DQ layer then
-- flags the record using the original raw value.

CREATE FUNCTION util.try_date(val text, fmt text) RETURNS date
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE d date;
BEGIN
    IF val IS NULL OR btrim(val) = '' THEN RETURN NULL; END IF;
    d := to_date(btrim(val), fmt);
    -- to_date is lenient in places; round-trip to reject anything it "fixed"
    IF to_char(d, fmt) <> btrim(val) THEN RETURN NULL; END IF;
    RETURN d;
EXCEPTION WHEN others THEN
    RETURN NULL;
END $$;

-- SuccessFactors OData dates look like /Date(1234567890000)/ (epoch milliseconds)
CREATE FUNCTION util.sf_date(val text) RETURNS date
LANGUAGE sql IMMUTABLE AS $$
    SELECT (to_timestamp((substring(val FROM '^/Date\((-?\d+)\)/$'))::bigint / 1000.0)
            AT TIME ZONE 'UTC')::date
$$;

CREATE FUNCTION util.try_numeric(val text) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    IF val IS NULL OR btrim(val) = '' THEN RETURN NULL; END IF;
    RETURN btrim(val)::numeric;
EXCEPTION WHEN others THEN
    RETURN NULL;
END $$;

-- "  ANNA " -> "Anna"
CREATE FUNCTION util.clean_name(val text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT NULLIF(initcap(btrim(regexp_replace(val, '\s+', ' ', 'g'))), '')
$$;
