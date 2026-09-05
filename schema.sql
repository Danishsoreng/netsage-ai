-- NetSage AI - PostgreSQL schema
-- The application creates these tables automatically via SQLAlchemy.
-- This file is the same schema written out by hand, for reference and for
-- anyone who prefers to provision the database up front.

CREATE TABLE IF NOT EXISTS cases (
    id                SERIAL PRIMARY KEY,
    case_ref          VARCHAR(32) UNIQUE NOT NULL,
    symptom           TEXT NOT NULL,
    topology_notes    TEXT DEFAULT '',
    show_output       TEXT DEFAULT '',
    actual_root_cause TEXT DEFAULT '',
    actual_fault_type VARCHAR(32) DEFAULT '',
    actual_osi_layer  VARCHAR(16) DEFAULT '',
    severity          VARCHAR(16) DEFAULT 'medium',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cases_ref ON cases (case_ref);

CREATE TABLE IF NOT EXISTS rule_findings (
    id         SERIAL PRIMARY KEY,
    case_id    INTEGER NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
    rule_code  VARCHAR(48) NOT NULL,
    severity   VARCHAR(16) DEFAULT 'medium',
    message    TEXT NOT NULL,
    evidence   TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_findings_case ON rule_findings (case_id);

CREATE TABLE IF NOT EXISTS diagnoses (
    id           SERIAL PRIMARY KEY,
    case_id      INTEGER NOT NULL REFERENCES cases (id) ON DELETE CASCADE,
    root_cause   TEXT NOT NULL,
    fault_type   VARCHAR(32) DEFAULT '',
    osi_layer    VARCHAR(16) DEFAULT '',
    confidence   DOUBLE PRECISION DEFAULT 0.0,
    evidence     TEXT DEFAULT '',
    next_command TEXT DEFAULT '',
    fix_steps    TEXT DEFAULT '',
    engine       VARCHAR(24) DEFAULT 'heuristic',
    raw_response TEXT DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_diagnoses_case ON diagnoses (case_id);

CREATE TABLE IF NOT EXISTS reviews (
    id                   SERIAL PRIMARY KEY,
    diagnosis_id         INTEGER NOT NULL UNIQUE REFERENCES diagnoses (id) ON DELETE CASCADE,
    decision             VARCHAR(16) NOT NULL,
    reviewer             VARCHAR(64) DEFAULT '',
    corrected_root_cause TEXT DEFAULT '',
    reviewer_notes       TEXT DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT NOW()
);
