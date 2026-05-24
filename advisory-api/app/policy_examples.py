"""
Example AI Policy Profile Configurations
Reference implementations for common tenant scenarios.
"""

# Example 1: High-security financial institution (SOC 2, strict remediation)
FINANCIAL_STRICT = {
    "org_id": "org-financial-001",
    "risk_tolerance": "low",  # Conservative risk assessment
    "verbosity": "detailed",  # Comprehensive explanations
    "compliance_mode": "soc2",  # SOC 2 alignment
    "remediation_style": "strict"  # Immediate, strict fixes
}

# Example 2: Healthcare provider (HIPAA, educational)
HEALTHCARE_EDUCATIONAL = {
    "org_id": "org-healthcare-001",
    "risk_tolerance": "medium",
    "verbosity": "detailed",  # Educational context important
    "compliance_mode": "hipaa",  # HIPAA alignment
    "remediation_style": "educational"  # Explain why steps matter
}

# Example 3: ISO 27001 certified organization
ISO_CERTIFIED = {
    "org_id": "org-iso-001",
    "risk_tolerance": "medium",
    "verbosity": "balanced",
    "compliance_mode": "iso",  # ISO 27001 alignment
    "remediation_style": "practical"  # Practical, implementable steps
}

# Example 4: Startup (fast-moving, practical)
STARTUP_PRACTICAL = {
    "org_id": "org-startup-001",
    "risk_tolerance": "high",  # Balance security with speed
    "verbosity": "concise",  # Quick, actionable advice
    "compliance_mode": "none",  # No specific compliance requirements
    "remediation_style": "practical"  # Focus on quick wins
}

# Example 5: Default (balanced, no compliance requirements)
DEFAULT_POLICY = {
    "org_id": "org-default",
    "risk_tolerance": "medium",
    "verbosity": "balanced",
    "compliance_mode": "none",
    "remediation_style": "practical"
}

# Usage example:
# from app.db.crud import create_or_update_policy_profile
# from app.db.database import SessionLocal
# 
# db = SessionLocal()
# policy = create_or_update_policy_profile(
#     db=db,
#     org_id="org-financial-001",
#     risk_tolerance="low",
#     verbosity="detailed",
#     compliance_mode="soc2",
#     remediation_style="strict"
# )

