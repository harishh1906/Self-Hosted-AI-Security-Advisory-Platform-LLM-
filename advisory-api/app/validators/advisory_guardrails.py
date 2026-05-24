def validate_advisory(advisory):
    """
    Validate AI-generated advisory against trust guarantees.
    Raises ValueError if validation fails.
    """
    # Confidence threshold check
    if advisory.confidence < 0.6:
        raise ValueError(f"Low confidence advisory: {advisory.confidence} < 0.6")
    
    # Severity must be valid
    valid_severities = ["Low", "Medium", "High", "Critical"]
    if advisory.severity not in valid_severities:
        raise ValueError(f"Invalid severity: {advisory.severity}. Must be one of {valid_severities}")
    
    # Risk summary must not be empty
    if not advisory.risk_summary or len(advisory.risk_summary.strip()) < 10:
        raise ValueError("Risk summary too short or empty")
    
    # Business impact must not be empty
    if not advisory.business_impact or len(advisory.business_impact.strip()) < 10:
        raise ValueError("Business impact too short or empty")
    
    # Must have at least one remediation step
    if not advisory.remediation_steps or len(advisory.remediation_steps) == 0:
        raise ValueError("No remediation steps provided")
    
    return True

