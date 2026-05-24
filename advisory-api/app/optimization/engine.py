"""
Model Optimization Engine
Analyzes AI usage patterns and recommends optimal models per organization and policy profile.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc, nullslast
from sqlalchemy.sql import case
from app.db.models import AICostAnalytics, AIModelOptimizationProfile, AuditLog, AIActiveModel
from app.db.database import SessionLocal
import uuid

logger = logging.getLogger(__name__)

# Model recommendations based on characteristics (Gemma 4 Ecosystem)
MODEL_RECOMMENDATIONS = {
    "cost_optimized": "gemma4:e2b",      # Efficient variant for local edge
    "latency_optimized": "gemma4:e2b",   # Fast inference for real-time needs
    "accuracy_optimized": "gemma4:31b",  # High-performance dense model for complex findings
    "balanced": "gemma4:e2b"             # Balanced production standard
}

# Thresholds for optimization recommendations
COST_HIGH_THRESHOLD = 0.001  # $0.001 per request
LATENCY_HIGH_THRESHOLD = 2000.0  # 2000ms
DRIFT_FREQUENCY_HIGH_THRESHOLD = 0.05  # 5% drift rate
BUDGET_UTILIZATION_WARNING = 80.0  # 80% budget utilization

# Import promotion thresholds from config
from app.config import (
    PROMOTION_CONFIDENCE_THRESHOLD,
    PROMOTION_SUCCESS_RATE_THRESHOLD,
    PROMOTION_LATENCY_MULTIPLIER,
    SLA_LATENCY_THRESHOLD_MS
)

def calculate_drift_frequency(
    org_id: str,
    policy_id: Optional[int],
    days: int = 30
) -> float:
    """
    Calculate drift frequency from audit logs.
    
    Args:
        org_id: Organization ID
        policy_id: Policy profile ID
        days: Number of days to analyze (default: 30)
    
    Returns:
        Drift frequency (0.0-1.0) - percentage of requests with drift detected
    """
    db: Session = SessionLocal()
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Query audit logs for drift detection
        total_requests = db.query(func.count(AuditLog.id)).filter(
            and_(
                AuditLog.org_id == org_id,
                AuditLog.policy_id == (policy_id if policy_id else None),
                AuditLog.action == "analyze_finding",
                AuditLog.created_at >= start_date
            )
        ).scalar() or 0
        
        if total_requests == 0:
            return 0.0
        
        # Count requests with drift detected
        # Query all relevant logs and filter in Python (PostgreSQL JSON query can be complex)
        all_logs = db.query(AuditLog).filter(
            and_(
                AuditLog.org_id == org_id,
                AuditLog.policy_id == (policy_id if policy_id else None),
                AuditLog.action == "analyze_finding",
                AuditLog.created_at >= start_date
            )
        ).all()
        
        drift_requests = sum(
            1 for log in all_logs
            if log.payload and log.payload.get("drift_status") == "DRIFT_DETECTED"
        )
        
        drift_frequency = drift_requests / total_requests if total_requests > 0 else 0.0
        return round(drift_frequency, 4)
        
    except Exception as e:
        logger.error(f"Failed to calculate drift frequency: {e}", exc_info=True)
        return 0.0
    finally:
        db.close()

def analyze_org_policy_performance(
    org_id: str,
    policy_id: Optional[int],
    days: int = 30
) -> Optional[Dict]:
    """
    Analyze last N days of analytics for an org+policy combination.
    
    Args:
        org_id: Organization ID
        policy_id: Policy profile ID
        days: Number of days to analyze (default: 30)
    
    Returns:
        Dictionary with analysis results or None if insufficient data
    """
    db: Session = SessionLocal()
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Query aggregated analytics including success rate
        result = db.query(
            func.avg(AICostAnalytics.estimated_cost_usd).label('avg_cost'),
            func.avg(AICostAnalytics.latency_ms).label('avg_latency'),
            func.count(AICostAnalytics.id).label('request_count'),
            func.sum(case((AICostAnalytics.success == 'success', 1), else_=0)).label('success_count')
        ).filter(
            and_(
                AICostAnalytics.org_id == org_id,
                AICostAnalytics.policy_id == (policy_id if policy_id else None),
                AICostAnalytics.endpoint == "analyze",
                AICostAnalytics.created_at >= start_date
            )
        ).first()
        
        if not result or result.request_count < 10:  # Need at least 10 requests
            return None
        
        avg_cost = float(result.avg_cost or 0.0)
        avg_latency = float(result.avg_latency or 0.0)
        request_count = int(result.request_count or 0)
        success_count = int(result.success_count or 0)
        
        # Calculate success rate
        success_rate = (success_count / request_count) if request_count > 0 else 0.0
        
        # Calculate drift frequency
        drift_frequency = calculate_drift_frequency(org_id, policy_id, days)
        
        # Calculate budget utilization (simplified - can be enhanced with actual budget data)
        # For now, we'll estimate based on cost trends
        # This would ideally come from a budget table
        budget_utilization = None  # Will be calculated if budget data available
        
        return {
            "avg_cost_per_request": round(avg_cost, 6),
            "avg_latency_ms": round(avg_latency, 2),
            "drift_frequency": drift_frequency,
            "request_count": request_count,
            "success_rate": round(success_rate, 4),
            "budget_utilization_percent": budget_utilization
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze performance: {e}", exc_info=True)
        return None
    finally:
        db.close()

def get_promotion_reason(
    avg_cost: float,
    avg_latency: float,
    drift_frequency: float,
    budget_utilization: Optional[float] = None
) -> str:
    """
    Get promotion reason based on performance characteristics.
    
    Returns:
        Promotion reason string
    """
    if budget_utilization and budget_utilization > BUDGET_UTILIZATION_WARNING:
        return "budget_optimization"
    
    if drift_frequency > DRIFT_FREQUENCY_HIGH_THRESHOLD:
        return "accuracy_optimization"
    
    if avg_latency > LATENCY_HIGH_THRESHOLD:
        return "latency_optimization"
    
    if avg_cost > COST_HIGH_THRESHOLD and avg_latency <= LATENCY_HIGH_THRESHOLD:
        return "cost_optimization"
    
    return "balanced_optimization"

def calculate_confidence(
    avg_cost: float,
    avg_latency: float,
    drift_frequency: float,
    request_count: int,
    budget_utilization: Optional[float] = None
) -> float:
    """
    Calculate confidence score (0.0-1.0) for model recommendation.
    
    Confidence is based on:
    - Sample size (more requests = higher confidence)
    - Clear optimization signals (strong signals = higher confidence)
    - Data quality (consistent data = higher confidence)
    
    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Base confidence from sample size
    if request_count < 10:
        return 0.0
    elif request_count < 50:
        sample_confidence = 0.5
    elif request_count < 200:
        sample_confidence = 0.75
    else:
        sample_confidence = 0.9
    
    # Signal strength (how clear the optimization need is)
    signal_strength = 0.0
    
    # Budget signal
    if budget_utilization and budget_utilization > BUDGET_UTILIZATION_WARNING:
        signal_strength = max(signal_strength, 0.95)
    
    # Drift signal
    if drift_frequency > DRIFT_FREQUENCY_HIGH_THRESHOLD:
        signal_strength = max(signal_strength, 0.9)
    
    # Latency signal
    if avg_latency > LATENCY_HIGH_THRESHOLD:
        signal_strength = max(signal_strength, 0.85)
    
    # Cost signal
    if avg_cost > COST_HIGH_THRESHOLD and avg_latency <= LATENCY_HIGH_THRESHOLD:
        signal_strength = max(signal_strength, 0.8)
    
    # If no strong signal, use balanced confidence
    if signal_strength == 0.0:
        signal_strength = 0.7
    
    # Combined confidence (weighted average)
    confidence = (sample_confidence * 0.4) + (signal_strength * 0.6)
    
    return round(min(confidence, 1.0), 2)

def recommend_model(
    avg_cost: float,
    avg_latency: float,
    drift_frequency: float,
    budget_utilization: Optional[float] = None
) -> str:
    """
    Recommend model based on performance characteristics.
    
    Args:
        avg_cost: Average cost per request
        avg_latency: Average latency in milliseconds
        drift_frequency: Frequency of drift detection (0.0-1.0)
        budget_utilization: Budget utilization percentage (optional)
    
    Returns:
        Recommended model name
    """
    # Decision logic:
    # 1. If cost is high but latency acceptable → recommend cheaper model
    # 2. If latency is high → recommend faster model
    # 3. If drift is frequent → recommend higher accuracy model
    # 4. If budget utilization > 80% → recommend optimization
    
    if budget_utilization and budget_utilization > BUDGET_UTILIZATION_WARNING:
        # Budget concern - optimize for cost
        return MODEL_RECOMMENDATIONS["cost_optimized"]
    
    if drift_frequency > DRIFT_FREQUENCY_HIGH_THRESHOLD:
        # High drift - prioritize accuracy
        return MODEL_RECOMMENDATIONS["accuracy_optimized"]
    
    if avg_latency > LATENCY_HIGH_THRESHOLD:
        # High latency - prioritize speed
        return MODEL_RECOMMENDATIONS["latency_optimized"]
    
    if avg_cost > COST_HIGH_THRESHOLD and avg_latency <= LATENCY_HIGH_THRESHOLD:
        # High cost but acceptable latency - optimize for cost
        return MODEL_RECOMMENDATIONS["cost_optimized"]
    
    # Default: balanced recommendation
    return MODEL_RECOMMENDATIONS["balanced"]

def generate_optimization_profile(
    org_id: str,
    policy_id: Optional[int]
) -> Optional[Dict]:
    """
    Generate optimization profile for an org+policy combination.
    
    Args:
        org_id: Organization ID
        policy_id: Policy profile ID
    
    Returns:
        Optimization profile dictionary or None if insufficient data
    """
    # Analyze last 30 days
    analysis = analyze_org_policy_performance(org_id, policy_id, days=30)
    
    if not analysis:
        return None
    
    # Recommend model based on analysis
    recommended_model = recommend_model(
        avg_cost=analysis["avg_cost_per_request"],
        avg_latency=analysis["avg_latency_ms"],
        drift_frequency=analysis["drift_frequency"],
        budget_utilization=analysis.get("budget_utilization_percent")
    )
    
    # Calculate confidence
    confidence = calculate_confidence(
        avg_cost=analysis["avg_cost_per_request"],
        avg_latency=analysis["avg_latency_ms"],
        drift_frequency=analysis["drift_frequency"],
        request_count=analysis["request_count"],
        budget_utilization=analysis.get("budget_utilization_percent")
    )
    
    # Get promotion reason
    promotion_reason = get_promotion_reason(
        avg_cost=analysis["avg_cost_per_request"],
        avg_latency=analysis["avg_latency_ms"],
        drift_frequency=analysis["drift_frequency"],
        budget_utilization=analysis.get("budget_utilization_percent")
    )
    
    return {
        "org_id": org_id,
        "policy_id": policy_id,
        "recommended_model": recommended_model,
        "avg_cost_per_request": analysis["avg_cost_per_request"],
        "avg_latency_ms": analysis["avg_latency_ms"],
        "drift_frequency": analysis["drift_frequency"],
        "budget_utilization_percent": analysis.get("budget_utilization_percent"),
        "confidence": confidence,
        "promotion_reason": promotion_reason
    }

def get_current_active_model(
    org_id: str,
    policy_id: Optional[int]
) -> Optional[str]:
    """
    Get currently active model for org+policy combination.
    
    Returns:
        Active model name or None if not set
    """
    db: Session = SessionLocal()
    try:
        active_model = db.query(AIActiveModel).filter(
            and_(
                AIActiveModel.org_id == org_id,
                AIActiveModel.policy_id == (policy_id if policy_id else None)
            )
        ).first()
        
        return active_model.active_model if active_model else None
        
    except Exception as e:
        logger.error(f"Failed to get active model: {e}", exc_info=True)
        return None
    finally:
        db.close()

def promote_model(
    org_id: str,
    policy_id: Optional[int],
    recommended_model: str,
    promotion_reason: str,
    confidence: float,
    correlation_id: Optional[str] = None,
    avg_latency_ms: Optional[float] = None
) -> Optional[AIActiveModel]:
    """
    Promote a model to active status for org+policy combination.
    
    Args:
        org_id: Organization ID
        policy_id: Policy profile ID
        recommended_model: Model to promote
        promotion_reason: Reason for promotion
        confidence: Confidence score
        correlation_id: Correlation ID for logging
        avg_latency_ms: Average latency for logging (optional)
    
    Returns:
        Updated active model record
    """
    db: Session = SessionLocal()
    try:
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Get or create active model record
        active_model = db.query(AIActiveModel).filter(
            and_(
                AIActiveModel.org_id == org_id,
                AIActiveModel.policy_id == (policy_id if policy_id else None)
            )
        ).first()
        
        if active_model:
            # Update existing
            active_model.active_model = recommended_model
            active_model.promotion_reason = promotion_reason
            active_model.confidence = confidence
            active_model.correlation_id = correlation_id
            active_model.last_promoted_at = datetime.now(timezone.utc)
        else:
            # Create new
            active_model = AIActiveModel(
                org_id=org_id,
                policy_id=policy_id,
                active_model=recommended_model,
                promotion_reason=promotion_reason,
                confidence=confidence,
                correlation_id=correlation_id
            )
            db.add(active_model)
        
        db.commit()
        db.refresh(active_model)
        
        # Log structured WARNING for promotion
        logger.warning(
            "Model promoted to active",
            extra={
                "message": "Model promoted to active",
                "org_id": org_id,
                "policy_id": policy_id,
                "active_model": recommended_model,
                "confidence": confidence,
                "avg_latency_ms": avg_latency_ms,
                "promotion_reason": promotion_reason,
                "correlation_id": correlation_id
            }
        )
        
        return active_model
        
    except Exception as e:
        logger.error(
            f"Failed to promote model: {e}",
            extra={
                "correlation_id": correlation_id,
                "org_id": org_id,
                "policy_id": policy_id
            },
            exc_info=True
        )
        db.rollback()
        return None
    finally:
        db.close()

def update_optimization_profile(
    org_id: str,
    policy_id: Optional[int],
    correlation_id: Optional[str] = None
) -> Optional[AIModelOptimizationProfile]:
    """
    Update or create optimization profile for an org+policy combination.
    Automatically promotes model if confidence ≥ 0.80 and model differs from current.
    When SLA is violated, promotion requires success_rate ≥ 0.95 AND latency ≤ 10x SLA threshold.
    
    Args:
        org_id: Organization ID
        policy_id: Policy profile ID
        correlation_id: Correlation ID for promotion logging
    
    Returns:
        Updated optimization profile or None if insufficient data
    """
    db: Session = SessionLocal()
    try:
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Generate optimization profile
        profile_data = generate_optimization_profile(org_id, policy_id)
        
        if not profile_data:
            return None
        
        # Get or create profile
        profile = db.query(AIModelOptimizationProfile).filter(
            and_(
                AIModelOptimizationProfile.org_id == org_id,
                AIModelOptimizationProfile.policy_id == (policy_id if policy_id else None)
            )
        ).first()
        
        if profile:
            # Update existing
            profile.recommended_model = profile_data["recommended_model"]
            profile.avg_cost_per_request = profile_data["avg_cost_per_request"]
            profile.avg_latency_ms = profile_data["avg_latency_ms"]
            profile.drift_frequency = profile_data["drift_frequency"]
            profile.budget_utilization_percent = profile_data.get("budget_utilization_percent")
        else:
            # Create new
            profile = AIModelOptimizationProfile(
                org_id=org_id,
                policy_id=policy_id,
                recommended_model=profile_data["recommended_model"],
                avg_cost_per_request=profile_data["avg_cost_per_request"],
                avg_latency_ms=profile_data["avg_latency_ms"],
                drift_frequency=profile_data["drift_frequency"],
                budget_utilization_percent=profile_data.get("budget_utilization_percent")
            )
            db.add(profile)
        
        db.commit()
        db.refresh(profile)
        
        # Auto-promote if conditions are met
        confidence = profile_data.get("confidence", 0.0)
        recommended_model = profile_data["recommended_model"]
        current_active_model = get_current_active_model(org_id, policy_id)
        avg_latency_ms = profile_data.get("avg_latency_ms", 0.0)
        success_rate = profile_data.get("success_rate", 1.0)
        
        # Check if model should be promoted
        should_promote = False
        promotion_reason = profile_data.get("promotion_reason", "auto_promotion")
        
        if confidence >= PROMOTION_CONFIDENCE_THRESHOLD:
            if current_active_model != recommended_model:
                # Check if SLA is violated
                sla_violated = avg_latency_ms > SLA_LATENCY_THRESHOLD_MS
                
                if sla_violated:
                    # SLA violated: require success_rate ≥ 0.95 AND latency ≤ 10x SLA
                    max_allowed_latency = SLA_LATENCY_THRESHOLD_MS * PROMOTION_LATENCY_MULTIPLIER
                    if success_rate >= PROMOTION_SUCCESS_RATE_THRESHOLD and avg_latency_ms <= max_allowed_latency:
                        should_promote = True
                        promotion_reason = f"{promotion_reason}_with_sla_violation"
                else:
                    # SLA not violated: promote if confidence threshold met
                    should_promote = True
                
                if should_promote:
                    # Auto-promote the recommended model
                    promote_model(
                        org_id=org_id,
                        policy_id=policy_id,
                        recommended_model=recommended_model,
                        promotion_reason=promotion_reason,
                        confidence=confidence,
                        correlation_id=correlation_id,
                        avg_latency_ms=avg_latency_ms
                    )
        
        return profile
        
    except Exception as e:
        logger.error(f"Failed to update optimization profile: {e}", exc_info=True)
        db.rollback()
        return None
    finally:
        db.close()

def get_active_models(
    org_id: str,
    policy_id: Optional[int] = None
) -> List[Dict]:
    """
    Get active models for an organization.
    Returns the latest promoted model per org+policy, or default MODEL_NAME if none exists.
    
    Args:
        org_id: Organization ID
        policy_id: Optional policy ID to filter by specific policy
    
    Returns:
        List of active model records (with default fallback if none exist)
    """
    from app.ollama_client import MODEL_NAME
    
    db: Session = SessionLocal()
    try:
        query = db.query(AIActiveModel).filter(
            AIActiveModel.org_id == org_id
        )
        
        if policy_id is not None:
            query = query.filter(
                AIActiveModel.policy_id == policy_id
            )
        
        # Order by last_promoted_at DESC, handling NULLs (newest first)
        active_models = query.order_by(
            nullslast(desc(AIActiveModel.last_promoted_at))
        ).all()
        
        results = []
        for model in active_models:
            results.append({
                "org_id": model.org_id,
                "policy_id": model.policy_id,
                "active_model": model.active_model,
                "promotion_reason": model.promotion_reason,
                "confidence": float(model.confidence or 0.0),
                "last_promoted_at": model.last_promoted_at.isoformat() if model.last_promoted_at else None,
                "correlation_id": model.correlation_id
            })
        
        # If no active models found, return default model
        if not results:
            default_result = {
                "org_id": org_id,
                "policy_id": policy_id,
                "active_model": MODEL_NAME,
                "promotion_reason": "default",
                "confidence": 0.0,
                "last_promoted_at": None,
                "correlation_id": None
            }
            results.append(default_result)
        
        return results
        
    except Exception as e:
        logger.error(f"Failed to get active models: {e}", exc_info=True)
        # Return default on error for graceful degradation
        from app.ollama_client import MODEL_NAME
        return [{
            "org_id": org_id,
            "policy_id": policy_id,
            "active_model": MODEL_NAME,
            "promotion_reason": "default",
            "confidence": 0.0,
            "last_promoted_at": None,
            "correlation_id": None
        }]
    finally:
        db.close()

def get_optimization_recommendations(
    org_id: str,
    policy_id: Optional[int] = None,
    correlation_id: Optional[str] = None
) -> List[Dict]:
    """
    Get optimization recommendations for an organization.
    
    Args:
        org_id: Organization ID
        policy_id: Optional policy ID to filter by specific policy
    
    Returns:
        List of optimization recommendations
    """
    db: Session = SessionLocal()
    try:
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Update profiles first (refresh recommendations and auto-promote)
        if policy_id is not None:
            # Update specific policy
            update_optimization_profile(org_id, policy_id, correlation_id)
        else:
            # Update all policies for this org
            # Get all unique policy_ids for this org from analytics
            policies = db.query(AICostAnalytics.policy_id).filter(
                AICostAnalytics.org_id == org_id
            ).distinct().all()
            
            # Update each policy (including None for default policy)
            for (pid,) in policies:
                update_optimization_profile(org_id, pid, correlation_id)
            
            # Also update default policy (None)
            update_optimization_profile(org_id, None, correlation_id)
        
        # Query recommendations
        query = db.query(AIModelOptimizationProfile).filter(
            AIModelOptimizationProfile.org_id == org_id
        )
        
        if policy_id is not None:
            query = query.filter(
                AIModelOptimizationProfile.policy_id == policy_id
            )
        
        profiles = query.all()
        
        recommendations = []
        for profile in profiles:
            recommendations.append({
                "org_id": profile.org_id,
                "policy_id": profile.policy_id,
                "recommended_model": profile.recommended_model,
                "avg_cost_per_request": float(profile.avg_cost_per_request or 0.0),
                "avg_latency_ms": float(profile.avg_latency_ms or 0.0),
                "drift_frequency": float(profile.drift_frequency or 0.0),
                "budget_utilization_percent": float(profile.budget_utilization_percent or 0.0) if profile.budget_utilization_percent else None
            })
        
        return recommendations
        
    except Exception as e:
        logger.error(f"Failed to get optimization recommendations: {e}", exc_info=True)
        return []
    finally:
        db.close()

