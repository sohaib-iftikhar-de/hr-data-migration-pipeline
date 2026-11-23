-- =====================================================================
-- Mapping (lookup) tables
-- In a real migration these are owned by the business analysts; keeping
-- them as data (not CASE statements buried in SQL) means a new code is a
-- one-row insert, not a code change.
-- =====================================================================

CREATE TABLE mapping.job_profile (
    source_system text NOT NULL,
    source_code   text NOT NULL,
    job_profile   text NOT NULL,
    PRIMARY KEY (source_system, source_code)
);

INSERT INTO mapping.job_profile VALUES
    ('EU',   '50000101', 'Software Engineer II'),
    ('EU',   '50000102', 'Senior Software Engineer'),
    ('EU',   '50000201', 'Financial Analyst'),
    ('EU',   '50000301', 'HR Business Partner'),
    ('EU',   '50000302', 'Operations Manager'),
    ('NA',   'ENG.JR',   'Software Engineer II'),
    ('NA',   'ENG.SR',   'Senior Software Engineer'),
    ('NA',   'FIN.ANL',  'Financial Analyst'),
    ('NA',   'HR.BP',    'HR Business Partner'),
    ('NA',   'OPS.MGR',  'Operations Manager'),
    ('APAC', 'J-101',    'Software Engineer II'),
    ('APAC', 'J-102',    'Senior Software Engineer'),
    ('APAC', 'J-201',    'Financial Analyst'),
    ('APAC', 'J-301',    'HR Business Partner'),
    ('APAC', 'J-302',    'Operations Manager');

-- Sources use ISO-2 or ISO-3; the target wants ISO-2
CREATE TABLE mapping.country (
    source_code text PRIMARY KEY,
    iso2        char(2) NOT NULL,
    name        text    NOT NULL
);

INSERT INTO mapping.country VALUES
    ('DE', 'DE', 'Germany'),   ('NO', 'NO', 'Norway'),    ('CH', 'CH', 'Switzerland'),
    ('US', 'US', 'United States'), ('CA', 'CA', 'Canada'),
    ('AUS', 'AU', 'Australia'), ('SGP', 'SG', 'Singapore'), ('JPN', 'JP', 'Japan');

CREATE TABLE mapping.worker_status (
    source_system text NOT NULL,
    source_code   text NOT NULL,
    status        text NOT NULL CHECK (status IN ('Active', 'Terminated')),
    PRIMARY KEY (source_system, source_code)
);

INSERT INTO mapping.worker_status VALUES
    ('EU',   '3',             'Active'),
    ('EU',   '0',             'Terminated'),
    ('NA',   'ACTIVE_ASSIGN', 'Active'),
    ('NA',   'TERM_ASSIGN',   'Terminated'),
    ('APAC', 'A',             'Active'),
    ('APAC', 'T',             'Terminated');
