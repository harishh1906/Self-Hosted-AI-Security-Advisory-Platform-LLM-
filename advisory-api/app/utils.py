import re
import json
import logging
from app.metrics import metrics

logger = logging.getLogger(__name__)

def extract_section(text: str, section: str) -> str:
    pattern = rf"{section}:\s*(.*?)(?=\n[A-Z_]+:|\n---END---|\Z)"
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""

def parse_advisory_output(text: str) -> dict:
    """
    Parse LLM output, prioritizing JSON format with fallback to text format.
    """
    # Strip any leading/trailing whitespace
    text = text.strip()
    
    # Try JSON parsing first (expected format from Gemma 4 with format: "json")
    try:
        # Remove any markdown code fences if present
        if text.startswith("```"):
            # Extract JSON from markdown code block
            text = re.sub(r"^```(?:json)?\s*\n", "", text)
            text = re.sub(r"\n```\s*$", "", text)
        
        parsed_json = json.loads(text)
        
        # Validate required fields
        if not isinstance(parsed_json, dict):
            raise ValueError("JSON output is not an object")
        
        # Extract and validate fields
        risk_summary = parsed_json.get("risk_summary", "")
        business_impact = parsed_json.get("business_impact", "")
        severity = parsed_json.get("severity", "Medium")
        remediation_steps = parsed_json.get("remediation_steps", [])
        confidence_raw = parsed_json.get("confidence", 0.6)
        
        # Ensure remediation_steps is a list
        if not isinstance(remediation_steps, list):
            remediation_steps = [str(remediation_steps)] if remediation_steps else []
        
        # Parse confidence
        try:
            confidence = float(confidence_raw)
            # Clamp between 0 and 1
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.6  # safe enterprise default
            logger.warning(f"Invalid confidence value in JSON: {confidence_raw}, using default 0.6")
            metrics.increment("llm_hallucination_count")
        
        # Validate severity
        valid_severities = ["Low", "Medium", "High", "Critical"]
        if severity not in valid_severities:
            severity = "Medium"
            logger.warning(f"Invalid severity in JSON, using default: Medium")
            metrics.increment("llm_hallucination_count")
        
        return {
            "risk_summary": risk_summary or "Risk summary not explicitly provided.",
            "business_impact": business_impact or "Business impact requires review.",
            "severity": severity,
            "remediation_steps": remediation_steps,
            "confidence": confidence
        }
    
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        # Fallback to text parsing for backward compatibility
        logger.warning(
            f"JSON parsing failed, falling back to text format parser",
            extra={"error": str(e), "output_preview": text[:200]}
        )
        
        # Original text-based parsing as fallback
        risk_summary = extract_section(text, "RISK_SUMMARY")
        business_impact = extract_section(text, "BUSINESS_IMPACT")
        severity = extract_section(text, "SEVERITY")
        confidence_raw = extract_section(text, "CONFIDENCE")
        remediation_raw = extract_section(text, "REMEDIATION_STEPS")

        remediation_steps = [
            re.sub(r"^\d+\.\s*", "", line).strip()
            for line in remediation_raw.splitlines()
            if line.strip()
        ]

        try:
            confidence = float(confidence_raw)
            confidence = max(0.0, min(1.0, confidence))  # Clamp between 0 and 1
        except Exception:
            confidence = 0.6  # safe enterprise default

        # Validate severity
        valid_severities = ["Low", "Medium", "High", "Critical"]
        if severity not in valid_severities:
            severity = "Medium"

        return {
            "risk_summary": risk_summary or "Risk summary not explicitly provided.",
            "business_impact": business_impact or "Business impact requires review.",
            "severity": severity,
            "remediation_steps": remediation_steps,
            "confidence": confidence
        }
