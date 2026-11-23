-- =====================================================================
-- DATA QUALITY RULES
-- Every rule writes one row per failing record into dq.rule_failure.
--   severity 'error'   -> record is rejected (would fail the target load)
--   severity 'warning' -> record is migrated, but flagged for review
-- Adding a rule = adding one INSERT below; the report picks it up automatically.
-- =====================================================================

DROP TABLE IF EXISTS dq.rule_failure;

CREATE TABLE dq.rule_failure (
    source_system text NOT NULL,
    source_id     text,
    rule          text NOT NULL,
    severity      text NOT NULL CHECK (severity IN ('error', 'warning')),
    detail        text
);

-- ---------------------------------------------------------- identity
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'missing_source_id', 'error', 'record has no source ID'
FROM staging.worker WHERE source_id IS NULL;

-- Same ID, different data: we can't know which version is correct, so both are
-- rejected and sent back to the business rather than guessing.
INSERT INTO dq.rule_failure
SELECT w.source_system, w.source_id, 'conflicting_duplicate_id', 'error',
       'ID appears ' || d.n || ' times with different values'
FROM staging.worker w
JOIN (SELECT source_system, source_id, count(*) AS n
      FROM staging.worker WHERE source_id IS NOT NULL
      GROUP BY 1, 2 HAVING count(*) > 1) d USING (source_system, source_id);

-- ---------------------------------------------------------- names
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'missing_name', 'error',
       'first_name=' || coalesce(first_name, '<null>') || ', last_name=' || coalesce(last_name, '<null>')
FROM staging.worker WHERE first_name IS NULL OR last_name IS NULL;

-- ---------------------------------------------------------- dates
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'invalid_birth_date', 'error',
       'raw value: ' || coalesce(nullif(birth_date_raw, ''), '<blank>')
FROM staging.worker WHERE birth_date IS NULL;

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'implausible_birth_date', 'error',
       'birth_date=' || birth_date || ' (age must be 16-100)'
FROM staging.worker
WHERE birth_date IS NOT NULL
  AND (birth_date > current_date - INTERVAL '16 years' OR birth_date < current_date - INTERVAL '100 years');

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'invalid_hire_date', 'error',
       'raw value: ' || coalesce(nullif(hire_date_raw, ''), '<blank>')
FROM staging.worker WHERE hire_date IS NULL;

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'invalid_end_date', 'error', 'raw value: ' || end_date_raw
FROM staging.worker WHERE end_date IS NULL AND nullif(end_date_raw, '') IS NOT NULL;

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'end_before_hire', 'error',
       'hire_date=' || hire_date || ', end_date=' || end_date
FROM staging.worker WHERE end_date < hire_date;

-- ---------------------------------------------------------- lookups
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'unmapped_job_code', 'error', 'job code: ' || coalesce(job_code_raw, '<null>')
FROM staging.worker WHERE job_profile IS NULL;

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'unmapped_country', 'error', 'country: ' || coalesce(country_raw, '<null>')
FROM staging.worker WHERE country_iso2 IS NULL;

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'unmapped_status', 'error', 'status: ' || coalesce(status_raw, '<null>')
FROM staging.worker WHERE status IS NULL;

-- ---------------------------------------------------------- consistency
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'status_end_date_mismatch', 'error',
       'status=' || status || ', end_date=' || coalesce(end_date::text, '<open>')
FROM staging.worker
WHERE (status = 'Terminated' AND end_date IS NULL)
   OR (status = 'Active' AND end_date IS NOT NULL AND end_date < current_date);

-- ---------------------------------------------------------- compensation
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'invalid_salary', 'error', 'raw value: ' || coalesce(salary_raw, '<null>')
FROM staging.worker WHERE annual_salary IS NULL OR annual_salary <= 0;

-- ---------------------------------------------------------- warnings (migrate, but flag)
INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'invalid_email', 'warning', 'email: ' || coalesce(email, '<null>')
FROM staging.worker WHERE email IS NULL OR email !~ '^[^@\s]+@[^@\s]+\.[a-z]{2,}$';

INSERT INTO dq.rule_failure
SELECT source_system, source_id, 'gender_unknown', 'warning', 'gender not provided by source'
FROM staging.worker WHERE gender = 'Unknown';
