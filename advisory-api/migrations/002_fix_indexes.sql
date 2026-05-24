-- Fix indexes for JSON type (not JSONB)
-- Run with: docker exec -i virtue-postgres psql -U virtue -d virtue < advisory-api/migrations/fix_indexes.sql

-- Drop any failed GIN indexes if they exist (ignore errors)
DROP INDEX IF EXISTS idx_audit_logs_model_name_used;
DROP INDEX IF EXISTS idx_audit_logs_actual_model_used;
DROP INDEX IF EXISTS idx_audit_logs_drift_status;
DROP INDEX IF EXISTS idx_audit_logs_model_selection;

-- Create expression indexes for JSON type (using ->> operator for text extraction)
CREATE INDEX IF NOT EXISTS idx_audit_logs_model_name_used ON audit_logs ((payload->>'model_name_used'));

CREATE INDEX IF NOT EXISTS idx_audit_logs_actual_model_used ON audit_logs ((payload->>'actual_model_used'));

CREATE INDEX IF NOT EXISTS idx_audit_logs_drift_status ON audit_logs ((payload->>'drift_status'));

CREATE INDEX IF NOT EXISTS idx_audit_logs_finding_title ON audit_logs ((payload->>'finding_title'));

-- Partial index for drift queries (more efficient)
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created_drift ON audit_logs (org_id, created_at) WHERE (payload->>'drift_status') = 'DRIFT_DETECTED';


