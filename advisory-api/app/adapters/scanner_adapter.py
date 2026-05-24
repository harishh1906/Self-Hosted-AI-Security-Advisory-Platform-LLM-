"""
Scanner Adapter - Converts scanner-style inputs to FindingInput format
Ensures compatibility with scanner platform workflows while maintaining validation.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.schemas import FindingInput

class ScannerFindingInput(BaseModel):
    """Scanner platform input format"""
    template_id: Optional[str] = Field(None, max_length=100)
    severity: Optional[str] = Field(None, max_length=50)
    url: Optional[str] = Field(None, max_length=2000)
    existing_description: str = Field(..., max_length=10000, min_length=1)
    technology_stack: Optional[str] = Field(None, max_length=500)
    org_id: Optional[str] = Field(
        None,
        pattern=r'^[a-zA-Z0-9_-]+$',
        min_length=1,
        max_length=100
    )
    
    @field_validator('severity')
    def validate_severity(cls, v):
        if v is not None:
            valid_severities = ["Low", "Medium", "High", "Critical"]
            if v not in valid_severities:
                raise ValueError(f"severity must be one of {valid_severities}")
        return v

def adapt_scanner_to_finding(scanner_input: ScannerFindingInput, scanner_name: str = "scanner-platform") -> FindingInput:
    """
    Convert scanner-style input to FindingInput format.
    
    Mapping:
    - template_id → title (with fallback)
    - existing_description → description
    - severity → severity
    - url → affected_asset
    - technology_stack → evidence (contextual info)
    - org_id → org_id
    
    Args:
        scanner_input: ScannerFindingInput from scanner platform
        scanner_name: Name of the scanner service (default: "scanner-platform")
    
    Returns:
        FindingInput ready for advisory generation
    """
    # Build title from template_id or use description excerpt
    if scanner_input.template_id:
        title = scanner_input.template_id
    else:
        # Use first 100 chars of description as title fallback
        title = scanner_input.existing_description[:100].strip()
        if len(scanner_input.existing_description) > 100:
            title += "..."
    
    # Build evidence from technology_stack and url
    evidence_parts = []
    if scanner_input.url:
        evidence_parts.append(f"URL: {scanner_input.url}")
    if scanner_input.technology_stack:
        evidence_parts.append(f"Technology: {scanner_input.technology_stack}")
    
    evidence = "\n".join(evidence_parts) if evidence_parts else None
    
    return FindingInput(
        title=title[:500],  # Enforce max length
        description=scanner_input.existing_description[:10000],  # Enforce max length
        severity=scanner_input.severity,
        evidence=evidence[:5000] if evidence else None,  # Enforce max length
        affected_asset=scanner_input.url[:200] if scanner_input.url else None,  # Enforce max length
        scanner=scanner_name,
        org_id=scanner_input.org_id
    )

