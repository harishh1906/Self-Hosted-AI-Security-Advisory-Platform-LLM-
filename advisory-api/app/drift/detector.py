"""
AI Output Drift Detection
Detects slow degradation and behavior changes in AI outputs over time.
"""
import logging
import statistics
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.db.models import Advisory, AIOutputBaseline
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

# Import configurable drift thresholds
from app.config import DRIFT_THRESHOLDS

def extract_metrics(advisory_result: Dict) -> Dict:
    """
    Extract metrics from advisory result for drift detection.
    No content storage - metrics only.
    
    Handles both dict and Pydantic model objects.
    """
    advisory = advisory_result.get("advisory", {})
    risk_assessment = advisory_result.get("risk_assessment", {})
    
    # Handle Pydantic model objects (use attribute access) or dict (use .get())
    if hasattr(advisory, 'confidence'):
        # Pydantic model
        confidence = advisory.confidence
        remediation_steps = advisory.remediation_steps if hasattr(advisory, 'remediation_steps') else []
        risk_summary = advisory.risk_summary if hasattr(advisory, 'risk_summary') else ""
        business_impact = advisory.business_impact if hasattr(advisory, 'business_impact') else ""
        severity = advisory.severity if hasattr(advisory, 'severity') else "Unknown"
    else:
        # Dict
        confidence = advisory.get("confidence", 0.0) if isinstance(advisory, dict) else 0.0
        remediation_steps = advisory.get("remediation_steps", []) if isinstance(advisory, dict) else []
        risk_summary = advisory.get("risk_summary", "") if isinstance(advisory, dict) else ""
        business_impact = advisory.get("business_impact", "") if isinstance(advisory, dict) else ""
        severity = advisory.get("severity", "Unknown") if isinstance(advisory, dict) else "Unknown"
    
    # Handle risk_assessment (dict or Pydantic model)
    if hasattr(risk_assessment, 'risk_score'):
        # Pydantic model
        risk_score = risk_assessment.risk_score
    else:
        # Dict
        risk_score = risk_assessment.get("risk_score", 0) if isinstance(risk_assessment, dict) else 0
    
    return {
        "confidence": float(confidence) if confidence is not None else 0.0,
        "remediation_steps_count": len(remediation_steps) if remediation_steps else 0,
        "description_length": len(str(risk_summary)) + len(str(business_impact)),
        "severity": str(severity) if severity else "Unknown",
        "risk_score": int(risk_score) if risk_score is not None else 0
    }

def calculate_distribution_shift(
    baseline_dist: Dict[str, float],
    current_dist: Dict[str, float]
) -> float:
    """
    Calculate distribution shift percentage.
    Returns maximum absolute difference across all categories.
    """
    if not baseline_dist or not current_dist:
        return 0.0
    
    all_keys = set(baseline_dist.keys()) | set(current_dist.keys())
    max_shift = 0.0
    
    for key in all_keys:
        baseline_val = baseline_dist.get(key, 0.0)
        current_val = current_dist.get(key, 0.0)
        shift = abs(current_val - baseline_val)
        max_shift = max(max_shift, shift)
    
    return max_shift * 100  # Convert to percentage

def detect_drift(
    endpoint: str,
    policy_id: Optional[int],
    advisory_result: Dict,
    org_id: str,
    correlation_id: str
) -> Tuple[str, List[str]]:
    """
    Detect drift in AI output compared to baseline.
    
    Args:
        endpoint: Endpoint name (e.g., "analyze")
        policy_id: Policy profile ID (None for default)
        advisory_result: Current advisory result
        org_id: Organization ID
        correlation_id: Request correlation ID
    
    Returns:
        tuple: (status, reason_codes)
        - status: "DRIFT_DETECTED" or "STABLE"
        - reason_codes: List of machine-readable drift reasons
    """
    # Extract metrics from current output
    current_metrics = extract_metrics(advisory_result)
    
    # Load baseline
    db: Session = SessionLocal()
    try:
        baseline = db.query(AIOutputBaseline).filter(
            and_(
                AIOutputBaseline.endpoint == endpoint,
                AIOutputBaseline.policy_id == (policy_id if policy_id else None),
                AIOutputBaseline.org_id == org_id
            )
        ).first()
        
        if not baseline or baseline.sample_count < DRIFT_THRESHOLDS["min_samples_for_baseline"]:
            # Not enough baseline data, skip drift detection
            logger.info(
                f"Insufficient baseline data for drift detection",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "endpoint": endpoint,
                    "policy_id": policy_id,
                    "sample_count": baseline.sample_count if baseline else 0
                }
            )
            return "STABLE", ["INSUFFICIENT_BASELINE_DATA"]
        
        reason_codes = []
        
        # 1. Check confidence drop
        if baseline.confidence_median and current_metrics["confidence"]:
            confidence_drop = baseline.confidence_median - current_metrics["confidence"]
            confidence_drop_percent = (confidence_drop / baseline.confidence_median) * 100 if baseline.confidence_median > 0 else 0
            
            if confidence_drop_percent > DRIFT_THRESHOLDS["confidence_drop_percent"]:
                reason_codes.append(f"CONFIDENCE_DROP_{confidence_drop_percent:.1f}%")
        
        # 2. Check remediation steps variance
        if baseline.remediation_steps_count_median and current_metrics["remediation_steps_count"]:
            steps_diff = abs(current_metrics["remediation_steps_count"] - baseline.remediation_steps_count_median)
            steps_variance_percent = (steps_diff / baseline.remediation_steps_count_median) * 100 if baseline.remediation_steps_count_median > 0 else 0
            
            if steps_variance_percent > DRIFT_THRESHOLDS["remediation_steps_variance_percent"]:
                reason_codes.append(f"REMEDIATION_STEPS_VARIANCE_{steps_variance_percent:.1f}%")
        
        # 3. Check severity distribution shift
        if baseline.severity_distribution:
            current_severity = current_metrics["severity"]
            current_dist = {current_severity: 1.0}  # Simplified: current single observation
            # For proper comparison, we'd need 24h distribution, but for single observation:
            # Check if current severity is significantly different from baseline
            baseline_severity_prob = baseline.severity_distribution.get(current_severity, 0.0)
            if baseline_severity_prob < DRIFT_THRESHOLDS["severity_distribution_shift_threshold"]:
                reason_codes.append(f"SEVERITY_DISTRIBUTION_SHIFT_{current_severity}")
        
        # 4. Check risk score median shift
        if baseline.risk_score_distribution:
            baseline_median = baseline.risk_score_distribution.get("median", 0)
            current_risk_score = current_metrics["risk_score"]
            risk_score_shift = abs(current_risk_score - baseline_median)
            
            if risk_score_shift > DRIFT_THRESHOLDS["risk_score_median_shift_points"]:
                reason_codes.append(f"RISK_SCORE_SHIFT_{risk_score_shift:.0f}_POINTS")
        
        # Determine status
        if reason_codes:
            status = "DRIFT_DETECTED"
            logger.warning(
                f"AI output drift detected",
                extra={
                    "correlation_id": correlation_id,
                    "org_id": org_id,
                    "policy_id": policy_id,
                    "endpoint": endpoint,
                    "reason_codes": reason_codes,
                    "current_confidence": current_metrics["confidence"],
                    "baseline_confidence": baseline.confidence_median
                }
            )
        else:
            status = "STABLE"
        
        return status, reason_codes
        
    except Exception as e:
        logger.error(f"Error in drift detection: {e}", exc_info=True)
        return "STABLE", []  # Fail safe: don't block on drift detection errors
    finally:
        db.close()

def calculate_baseline_from_audit_logs(
    endpoint: str,
    policy_id: Optional[int],
    org_id: str,
    db: Session
) -> Optional[Dict]:
    """
    Calculate baseline from audit logs (last 7 days).
    Returns baseline metrics dict or None if insufficient data.
    """
    from app.db.models import AuditLog
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    # Query audit logs for this endpoint, policy, and org (last 7 days)
    logs = db.query(AuditLog).filter(
        and_(
            AuditLog.action == "analyze_finding",
            AuditLog.policy_id == (policy_id if policy_id else None),
            AuditLog.org_id == org_id,
            AuditLog.created_at >= seven_days_ago
        )
    ).all()
    
    if len(logs) < DRIFT_THRESHOLDS["min_samples_for_baseline"]:
        return None
    
    # Extract metrics from audit log payloads
    confidences = []
    remediation_counts = []
    description_lengths = []
    severities = []
    risk_scores = []
    
    for log in logs:
        payload = log.payload or {}
        if payload.get("confidence") is not None:
            confidences.append(payload["confidence"])
        if payload.get("risk_score") is not None:
            risk_scores.append(payload["risk_score"])
        if payload.get("remediation_steps_count") is not None:
            remediation_counts.append(payload["remediation_steps_count"])
        if payload.get("description_length") is not None:
            description_lengths.append(payload["description_length"])
        if payload.get("severity"):
            severities.append(payload["severity"])
    
    if not confidences or not risk_scores:
        return None
    
    # Calculate medians
    confidence_median = statistics.median(confidences) if confidences else None
    risk_score_median = statistics.median(risk_scores) if risk_scores else None
    remediation_steps_count_median = statistics.median(remediation_counts) if remediation_counts else None
    description_length_median = statistics.median(description_lengths) if description_lengths else None
    
    # Calculate severity distribution
    severity_counts = {}
    for severity in severities:
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    
    total = sum(severity_counts.values())
    severity_distribution = {
        k: v / total for k, v in severity_counts.items()
    } if total > 0 else {}
    
    # Risk score distribution
    risk_scores_sorted = sorted(risk_scores)
    risk_score_distribution = {
        "median": risk_score_median,
        "p25": risk_scores_sorted[len(risk_scores_sorted) // 4] if len(risk_scores_sorted) >= 4 else risk_score_median,
        "p75": risk_scores_sorted[3 * len(risk_scores_sorted) // 4] if len(risk_scores_sorted) >= 4 else risk_score_median
    }
    
    return {
        "confidence_median": confidence_median,
        "remediation_steps_count_median": remediation_steps_count_median,
        "description_length_median": description_length_median,
        "severity_distribution": severity_distribution,
        "risk_score_distribution": risk_score_distribution,
        "sample_count": len(logs)
    }

def update_baseline(
    endpoint: str,
    policy_id: Optional[int],
    advisory_result: Dict,
    org_id: str
):
    """
    Update baseline with new advisory output.
    Recalculates from 7-day audit log window.
    """
    db: Session = SessionLocal()
    try:
        # Calculate baseline from audit logs
        baseline_data = calculate_baseline_from_audit_logs(endpoint, policy_id, org_id, db)
        
        if not baseline_data:
            # Not enough data yet, skip update
            return
        
        # Get or create baseline record
        baseline = db.query(AIOutputBaseline).filter(
            and_(
                AIOutputBaseline.endpoint == endpoint,
                AIOutputBaseline.policy_id == (policy_id if policy_id else None),
                AIOutputBaseline.org_id == org_id
            )
        ).first()
        
        if not baseline:
            baseline = AIOutputBaseline(
                org_id=org_id,
                endpoint=endpoint,
                policy_id=policy_id,
                confidence_median=baseline_data["confidence_median"],
                remediation_steps_count_median=baseline_data["remediation_steps_count_median"],
                description_length_median=baseline_data["description_length_median"],
                severity_distribution=baseline_data["severity_distribution"],
                risk_score_distribution=baseline_data["risk_score_distribution"],
                sample_count=baseline_data["sample_count"]
            )
            db.add(baseline)
        else:
            # Update with recalculated baseline
            baseline.confidence_median = baseline_data["confidence_median"]
            baseline.remediation_steps_count_median = baseline_data["remediation_steps_count_median"]
            baseline.description_length_median = baseline_data["description_length_median"]
            baseline.severity_distribution = baseline_data["severity_distribution"]
            baseline.risk_score_distribution = baseline_data["risk_score_distribution"]
            baseline.sample_count = baseline_data["sample_count"]
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Error updating baseline: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

