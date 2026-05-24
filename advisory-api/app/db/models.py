from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, UniqueConstraint
from sqlalchemy.sql import func
from app.db.database import Base

class Advisory(Base):
    __tablename__ = "advisories"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=True, index=True)  # Multi-tenancy isolation
    finding_title = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    risk_score = Column(Integer, nullable=False)
    advisory = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=True, index=True)  # Multi-tenancy isolation
    user_id = Column(String, nullable=True)
    service_name = Column(String, nullable=True)  # Service-to-service calls
    policy_id = Column(Integer, nullable=True, index=True)  # AI policy profile used
    action = Column(String, nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

class AIPolicyProfile(Base):
    __tablename__ = "ai_policy_profiles"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=False, unique=True, index=True)  # One policy per org
    risk_tolerance = Column(String, nullable=False, default="medium")  # low|medium|high
    verbosity = Column(String, nullable=False, default="balanced")  # concise|balanced|detailed
    compliance_mode = Column(String, nullable=False, default="none")  # none|soc2|iso|hipaa
    remediation_style = Column(String, nullable=False, default="practical")  # practical|strict|educational
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AIOutputBaseline(Base):
    __tablename__ = "ai_output_baselines"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=False, index=True)  # Multi-tenancy isolation
    endpoint = Column(String, nullable=False, default="analyze")  # Endpoint name
    policy_id = Column(Integer, nullable=True, index=True)  # Policy profile ID (None for default)
    
    # Rolling medians (7-day baseline)
    confidence_median = Column(Float, nullable=True)
    remediation_steps_count_median = Column(Float, nullable=True)
    description_length_median = Column(Float, nullable=True)
    
    # Distribution data (JSON)
    severity_distribution = Column(JSON, nullable=True)  # {"Low": 0.2, "Medium": 0.5, "High": 0.2, "Critical": 0.1}
    risk_score_distribution = Column(JSON, nullable=True)  # {"median": 65, "p25": 45, "p75": 85}
    
    # Metadata
    sample_count = Column(Integer, nullable=False, default=0)  # Number of samples in baseline
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Unique constraint: one baseline per (org_id, endpoint, policy_id) combination
    __table_args__ = (
        UniqueConstraint('org_id', 'endpoint', 'policy_id', name='uq_org_endpoint_policy'),
    )

class AICostAnalytics(Base):
    __tablename__ = "ai_cost_analytics"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=False, index=True)  # Multi-tenancy isolation
    endpoint = Column(String, nullable=False, default="analyze", index=True)  # Endpoint name
    policy_id = Column(Integer, nullable=True, index=True)  # Policy profile ID (None for default)
    
    # Policy metadata (denormalized for efficient querying)
    policy_risk_tolerance = Column(String, nullable=True)  # low|medium|high
    policy_verbosity = Column(String, nullable=True)  # concise|balanced|detailed
    policy_compliance_mode = Column(String, nullable=True)  # none|soc2|iso|hipaa
    
    # Cost and usage metrics
    tokens_used = Column(Integer, nullable=False, default=0)  # Total tokens (input + output)
    input_tokens = Column(Integer, nullable=True)  # Input tokens
    output_tokens = Column(Integer, nullable=True)  # Output tokens
    estimated_cost_usd = Column(Float, nullable=True)  # Estimated cost in USD
    
    # Performance metrics
    latency_ms = Column(Float, nullable=False)  # Request latency in milliseconds
    llm_latency_ms = Column(Float, nullable=True)  # LLM-only latency
    
    # Success metrics
    success = Column(String, nullable=False, default="success")  # success|failure|error
    error_type = Column(String, nullable=True)  # Error classification if failed
    
    # Model information
    model_name = Column(String, nullable=True, index=True)  # Model name used for this request
    
    # Metadata
    correlation_id = Column(String, nullable=True, index=True)  # Request correlation ID
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Tenant rating (for policy effectiveness tracking)
    tenant_rating = Column(Float, nullable=True)  # Rating from tenant (1.0-5.0)
    
    # Composite index for efficient querying by (org_id, endpoint, policy_id)
    __table_args__ = (
        {'comment': 'AI cost and performance analytics per policy configuration'}
    )

class AIModelOptimizationProfile(Base):
    __tablename__ = "ai_model_optimization_profiles"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=False, index=True)  # Multi-tenancy isolation
    policy_id = Column(Integer, nullable=True, index=True)  # Policy profile ID (None for default)
    
    # Optimization recommendations
    recommended_model = Column(String, nullable=False, default="mistral:7b-instruct")  # Recommended LLM model
    avg_cost_per_request = Column(Float, nullable=True)  # Average cost per request in USD
    avg_latency_ms = Column(Float, nullable=True)  # Average latency in milliseconds
    drift_frequency = Column(Float, nullable=True)  # Frequency of drift detection (0.0-1.0)
    budget_utilization_percent = Column(Float, nullable=True)  # Budget utilization percentage (0.0-100.0)
    
    # Metadata
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Unique constraint: one optimization profile per (org_id, policy_id) combination
    __table_args__ = (
        UniqueConstraint('org_id', 'policy_id', name='uq_org_policy_optimization'),
    )

class AIActiveModel(Base):
    __tablename__ = "ai_active_models"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(String, nullable=False, index=True)  # Multi-tenancy isolation
    policy_id = Column(Integer, nullable=True, index=True)  # Policy profile ID (None for default)
    
    # Active model information
    active_model = Column(String, nullable=False, default="mistral:7b-instruct")  # Currently active LLM model
    last_promoted_at = Column(DateTime(timezone=True), server_default=func.now())  # When model was last promoted
    promotion_reason = Column(String, nullable=True)  # Reason for promotion (e.g., "latency_optimization", "cost_optimization")
    confidence = Column(Float, nullable=False, default=0.0)  # Confidence score (0.0-1.0) for the promotion
    
    # Metadata
    correlation_id = Column(String, nullable=True, index=True)  # Correlation ID of promotion request
    
    # Unique constraint: one active model per (org_id, policy_id) combination
    __table_args__ = (
        UniqueConstraint('org_id', 'policy_id', name='uq_org_policy_active_model'),
    )

class ModelConfiguration(Base):
    """
    Cluster-wide model configuration for hot-reload consistency.
    Ensures all instances in a cluster use the same model configuration.
    """
    __tablename__ = "model_configurations"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String, nullable=False, unique=True, index=True)  # "default" or "org:{org_id}"
    model_name = Column(String, nullable=False)  # Model name
    enabled = Column(String, nullable=False, default="true")  # "true" or "false"
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by = Column(String, nullable=True)  # User/service that made the update
    correlation_id = Column(String, nullable=True)  # Correlation ID for the update

class SystemSettings(Base):
    """
    Centralized system configuration for workers, LLM routing, and performance SLAs.
    """
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String, unique=True, index=True, nullable=False)
    setting_value = Column(JSON, nullable=False)
    description = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
