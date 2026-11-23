-- =====================================================================
-- STAGING -> CURATED
-- Only records with no 'error' failures are promoted. Warnings travel with
-- the record so reviewers can see them in the target system.
-- =====================================================================

DROP TABLE IF EXISTS curated.worker;
DROP TABLE IF EXISTS dq.rejected_worker;

-- A staging row is rejected if its (source_system, source_id) has any error.
-- Rows without an ID can't be matched by key, so they're handled explicitly.
CREATE TABLE curated.worker AS
SELECT
    w.source_system || '-' || w.source_id           AS worker_id,
    w.source_system,
    w.source_id,
    w.first_name,
    w.last_name,
    w.gender,
    w.birth_date,
    w.hire_date,
    w.end_date,
    w.country_iso2,
    w.status,
    w.job_profile,
    w.annual_salary,
    w.currency,
    w.email,
    coalesce(warn.rules, '{}')                       AS dq_warnings,
    w.source_file
FROM staging.worker w
LEFT JOIN (
    SELECT source_system, source_id, array_agg(rule ORDER BY rule) AS rules
    FROM dq.rule_failure WHERE severity = 'warning'
    GROUP BY 1, 2
) warn USING (source_system, source_id)
WHERE w.source_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM dq.rule_failure f
      WHERE f.severity = 'error'
        AND f.source_system = w.source_system
        AND f.source_id = w.source_id);

ALTER TABLE curated.worker ADD PRIMARY KEY (worker_id);

-- Everything that didn't make it, with every reason, ready to send back to the business
CREATE TABLE dq.rejected_worker AS
SELECT
    w.source_system,
    w.source_id,
    w.first_name,
    w.last_name,
    w.source_file,
    array_agg(DISTINCT f.rule ORDER BY f.rule)                 AS failed_rules,
    string_agg(DISTINCT f.rule || ': ' || f.detail, ' | ')     AS details
FROM staging.worker w
JOIN dq.rule_failure f
  ON f.severity = 'error'
 AND f.source_system = w.source_system
 AND f.source_id IS NOT DISTINCT FROM w.source_id
GROUP BY w.source_system, w.source_id, w.first_name, w.last_name, w.source_file,
         -- keep conflicting duplicates as separate rows
         w.job_code_raw, w.salary_raw, w.email;
