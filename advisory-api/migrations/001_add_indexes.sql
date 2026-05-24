-- Add indexes for performance optimization
-- Run with: docker exec -it virtue-postgres psql -U virtue -d virtue -f /path/to/add_indexes.sql

-- Index on ai_cost_analytics.model_name for fast model queries
CREATE INDEX IF NOT EXISTS idx_ai_cost_analytics_model_name ON ai_cost_analytics(model_name);

-- Index on audit_logs payload for model_name_used queries (expression index for JSON)
-- Note: payload is JSON type, not JSONB, so we use expression indexes with ->> operator
CREATE INDEX IF NOT EXISTS idx_audit_logs_model_name_used ON audit_logs ((payload->>'model_name_used'));

-- Index on audit_logs payload for actual_model_used queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_actual_model_used ON audit_logs ((payload->>'actual_model_used'));

-- Index on audit_logs payload for drift_status queries
CREATE INDEX IF NOT EXISTS idx_audit_logs_drift_status ON audit_logs ((payload->>'drift_status'));

-- Index on audit_logs payload for finding_title queries (commonly queried)
CREATE INDEX IF NOT EXISTS idx_audit_logs_finding_title ON audit_logs ((payload->>'finding_title'));

-- Index on audit_logs for common query patterns (org_id + created_at + drift_status)
CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created_drift ON audit_logs (org_id, created_at) WHERE (payload->>'drift_status') = 'DRIFT_DETECTED';

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_ai_cost_analytics_org_model ON ai_cost_analytics(org_id, model_name, created_at);

