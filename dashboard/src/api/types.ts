// ── API Response Types for Virtue-AI Backend ──

export interface HealthResponse {
  status: 'ready' | 'not_ready';
  services: {
    ollama: {
      status: 'healthy' | 'degraded' | 'unhealthy';
      model_available: boolean;
      model_loaded: boolean;
      model_name: string;
      response_time_ms: number;
      error?: string;
    };
    qdrant: {
      status: 'healthy' | 'degraded' | 'unhealthy';
      collection_exists: boolean;
      collection_name: string;
      response_time_ms: number;
      error?: string;
    };
    postgres: {
      status: 'healthy' | 'unhealthy';
      response_time_ms: number;
      error?: string;
    };
  };
  circuit_breaker?: {
    state: 'closed' | 'open' | 'half_open';
    failure_rate: number;
    total_requests: number;
    successes: number;
    failures: number;
    recent_state_changes: Array<{
      timestamp: number;
      old_state: string;
      new_state: string;
      failure_rate: number;
      request_count: number;
    }>;
  };
}

export interface MetricsResponse {
  // Core counters
  requests_total: number;
  success_count: number;
  failures_total: number;
  degraded_total: number;
  fallback_count: number;
  drift_count: number;
  tokens_total: number;
  requests_per_second: number;
  // Latency — backend uses p95_latency for the key name, aliased below
  p50_latency_ms: number;
  p95_latency_ms: number;  // mapped from p95_latency in client
  p99_latency_ms: number;
  avg_latency_ms: number;
  // Optional fields that may not always be present
  min_latency_ms?: number;
  max_latency_ms?: number;
  latency_sample_count?: number;
}

export interface ConfidenceTrend {
  recent_avg: number;
  older_avg: number;
  drop_percent: number;
  is_declining: boolean;
  sample_count: number;
}

export interface ModelHealthSummary {
  model_name: string;
  usage_count: number;
  avg_latency_ms: number;
  fallback_count: number;
  drift_adjustments: number;
  drift_adjustment_rate: number;
  last_used_at: string | null;
  sla_violations: number;
  confidence_trend: ConfidenceTrend | null;
}

export interface OptimizationInsights {
  top_performing_models: Array<{
    model_name: string;
    avg_latency_ms: number;
    success_rate: number;
    total_requests: number;
    performance_score: number;
    rank: number;
  }>;
  fallback_usage_stats: {
    total_fallbacks: number;
    total_requests: number;
    overall_fallback_rate: number;
    models_with_fallbacks: Array<{
      model_name: string;
      fallback_count: number;
    }>;
  };
  drift_adjustment_trends: {
    total_drift_events: number;
    events_by_date: Record<string, number>;
    avg_events_per_day: number;
  };
  policy_profile_effectiveness: Array<{
    policy_id: number;
    avg_latency_ms: number;
    request_count: number;
    avg_confidence: number | null;
  }>;
  model_selection_decision_chains: Array<{
    correlation_id: string;
    org_id: string;
    policy_id: number | null;
    timestamp: string;
    selected_model: string;
    actual_model_used: string;
    used_fallback: boolean;
    decision_reason: string | null;
    response_time_ms: number | null;
    model_confidence: number | null;
  }>;
}

export interface PolicyCostSummary {
  policy_id: number | null;
  policy_risk_tolerance: string | null;
  policy_verbosity: string | null;
  policy_compliance_mode: string | null;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  request_count: number;
  avg_tokens_per_request: number;
  avg_cost_per_request_usd: number;
}

export interface PolicyLatencySummary {
  policy_id: number | null;
  policy_risk_tolerance: string | null;
  policy_verbosity: string | null;
  policy_compliance_mode: string | null;
  avg_latency_ms: number;
  avg_llm_latency_ms: number;
  min_latency_ms: number;
  max_latency_ms: number;
  request_count: number;
}

export interface PolicySuccessSummary {
  policy_id: number | null;
  policy_risk_tolerance: string | null;
  policy_verbosity: string | null;
  policy_compliance_mode: string | null;
  total_requests: number;
  success_count: number;
  failure_count: number;
  error_count: number;
  success_rate: number;
  failure_rate: number;
  error_rate: number;
}

export interface PolicyEffectiveness {
  policy_id: number;
  org_id: string;
  avg_confidence: number | null;
  avg_latency: number | null;
  drift_frequency: number;
  tenant_rating_average: number | null;
  request_count: number;
}

export interface ActiveModel {
  org_id: string;
  policy_id: number | null;
  active_model: string;
  promotion_reason: string;
  confidence: number;
  last_promoted_at: string | null;
  correlation_id: string | null;
}

export interface KnowledgeStats {
  qdrant: {
    collection: string;
    points_count: number;
    vectors_count: number;
    status: string;
    error?: string;
  };
  ingestion: {
    total_ingestion_runs: number;
    total_documents_created: number;
    total_documents_updated: number;
    last_ingestion_at: string | null;
    status?: string;
  };
}
