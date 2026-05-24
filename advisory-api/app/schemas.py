from pydantic import BaseModel, Field, field_validator
from typing import Optional
from typing import List
import re

class FindingInput(BaseModel):
    # HIGH PRIORITY FIX: Add strict input size limits
    title: str = Field(..., max_length=500, min_length=1)
    description: str = Field(..., max_length=10000, min_length=1)
    severity: Optional[str] = Field(None, max_length=50)
    evidence: Optional[str] = Field(None, max_length=5000)
    affected_asset: Optional[str] = Field(None, max_length=200)
    scanner: Optional[str] = Field(None, max_length=100)
    
    # HIGH PRIORITY FIX: Validate org_id format using pattern
    org_id: Optional[str] = Field(
        None,
        pattern=r'^[a-zA-Z0-9_-]+$',
        min_length=1,
        max_length=100,
        description="Organization ID (alphanumeric, hyphens, underscores only)"
    )
    
    # Adaptive serving: Optional model override
    active_model: Optional[str] = Field(
        None,
        max_length=100,
        description="Active model to use for advisory generation (overrides default)"
    )
    
    # Runtime rollback: Use default model instead of active_model
    rollback_flag: Optional[bool] = Field(
        None,
        description="If true, use default MODEL_NAME instead of active_model"
    )
    
    # Optimized policy instructions from scanner
    risk_tolerance: Optional[str] = Field(
        None,
        max_length=50,
        description="Risk tolerance override: low|medium|high"
    )
    verbosity: Optional[str] = Field(
        None,
        max_length=50,
        description="Verbosity override: concise|balanced|detailed"
    )
    remediation_style: Optional[str] = Field(
        None,
        max_length=50,
        description="Remediation style override: practical|strict|educational"
    )
    model_override: Optional[str] = Field(
        None,
        max_length=100,
        description="Model override from scanner (routes advisory to this model)"
    )
    
    # Explainable AI serving
    force_model: Optional[str] = Field(
        None,
        max_length=100,
        description="Force model override (primary, fallback still allowed)"
    )
    decision_reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for model/policy decision (for explainability)"
    )
    
    @field_validator('severity')
    def validate_severity(cls, v):
        if v is not None:
            valid_severities = ["Low", "Medium", "High", "Critical"]
            if v not in valid_severities:
                raise ValueError(f"severity must be one of {valid_severities}")
        return v
    
    @field_validator('risk_tolerance')
    def validate_risk_tolerance(cls, v):
        if v is not None:
            valid_tolerances = ["low", "medium", "high"]
            if v not in valid_tolerances:
                raise ValueError(f"risk_tolerance must be one of {valid_tolerances}")
        return v
    
    @field_validator('verbosity')
    def validate_verbosity(cls, v):
        if v is not None:
            valid_verbosities = ["concise", "balanced", "detailed"]
            if v not in valid_verbosities:
                raise ValueError(f"verbosity must be one of {valid_verbosities}")
        return v
    
    @field_validator('remediation_style')
    def validate_remediation_style(cls, v):
        if v is not None:
            valid_styles = ["practical", "strict", "educational"]
            if v not in valid_styles:
                raise ValueError(f"remediation_style must be one of {valid_styles}")
        return v

class AdvisoryStructuredResponse(BaseModel):
    risk_summary: str
    business_impact: str
    severity: str
    remediation_steps: List[str]
    confidence: float

class RiskAssessment(BaseModel):
    risk_score: int
    risk_level: str
    sla: str
    justification: str
