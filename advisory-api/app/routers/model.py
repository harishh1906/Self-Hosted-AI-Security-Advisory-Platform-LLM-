import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user_or_service
from app.model_manager import model_manager
from app.model_health import get_model_health_summary, model_health_tracker, SLA_LATENCY_THRESHOLD
from app.config import SLA_LATENCY_THRESHOLD_MS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Model Governance"])

@router.get("/internal/model-health")
def get_model_health(identity: dict = Depends(get_current_user_or_service)):
    """
    Get real-time health metrics per model from ai_cost_analytics.
    
    Returns per-model aggregated metrics:
    - model_name: Model identifier
    - usage_count: Total number of requests
    - avg_latency_ms: Average request latency
    - tokens_used_total: Total tokens used
    - fallback_count: Number of fallback events (from audit logs)
    - drift_adjustments: Number of drift adjustments (from audit logs)
    - sla_violations: Number of SLA violations (latency > SLA_LATENCY_THRESHOLD_MS)
    - last_used_at: ISO timestamp of last usage
    """
    from app.db.database import SessionLocal
    from sqlalchemy import func, and_, cast
    from sqlalchemy.dialects.postgresql import JSONB
    from datetime import datetime, timedelta, timezone
    from app.db.models import AICostAnalytics, AuditLog
    
    db: Session = SessionLocal()
    try:
        # Get model metrics from ai_cost_analytics (fast aggregation)
        model_stats = db.query(
            AICostAnalytics.model_name,
            func.count(AICostAnalytics.id).label('usage_count'),
            func.avg(AICostAnalytics.latency_ms).label('avg_latency'),
            func.sum(AICostAnalytics.tokens_used).label('tokens_total'),
            func.max(AICostAnalytics.created_at).label('last_used')
        ).filter(
            AICostAnalytics.model_name.isnot(None)
        ).group_by(
            AICostAnalytics.model_name
        ).all()
        
        # Get fallback and drift counts from audit logs (with timeout protection)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        models_list = []
        for stat in model_stats:
            model_name = stat.model_name
            if not model_name:
                continue
                
            # Count fallbacks and drift adjustments from audit logs
            try:
                # Use PostgreSQL JSONB operators properly for nested access
                jsonb_payload = cast(AuditLog.payload, JSONB)
                fallback_count = db.query(AuditLog).filter(
                    and_(
                        AuditLog.created_at >= thirty_days_ago,
                        jsonb_payload.has_key('model_selection'),
                        jsonb_payload['model_selection'].astext.cast(JSONB)['used_fallback'].astext == 'true',
                        jsonb_payload['actual_model_used'].astext == model_name
                    )
                ).count()
                
                drift_count = db.query(AuditLog).filter(
                    and_(
                        AuditLog.created_at >= thirty_days_ago,
                        jsonb_payload.has_key('drift_status'),
                        jsonb_payload['drift_status'].astext == 'DRIFT_DETECTED',
                        jsonb_payload['actual_model_used'].astext == model_name
                    )
                ).count()
            except Exception:
                # Graceful degradation if JSONB query fails
                fallback_count = 0
                drift_count = 0
            
            # Count SLA violations (latency > SLA threshold)
            sla_violations = db.query(AICostAnalytics).filter(
                and_(
                    AICostAnalytics.model_name == model_name,
                    AICostAnalytics.latency_ms > SLA_LATENCY_THRESHOLD_MS
                )
            ).count()
            
            models_list.append({
                "model_name": model_name,
                "usage_count": stat.usage_count,
                "avg_latency_ms": round(float(stat.avg_latency or 0), 2),
                "tokens_used_total": int(stat.tokens_total or 0),
                "fallback_count": fallback_count,
                "drift_adjustments": drift_count,
                "sla_violations": sla_violations,
                "last_used_at": stat.last_used.isoformat() if stat.last_used else None
            })
        
        return {"models": models_list}
    except Exception as e:
        logger.error(f"Error getting model health: {e}", exc_info=True)
        # Graceful degradation - return empty list
        return {"models": []}
    finally:
        db.close()

@router.get("/internal/control-plane/model-health-summary")
def get_model_health_summary_endpoint(identity: dict = Depends(get_current_user_or_service)):
    """
    Get real-time model health summary for control plane.
    
    Tracks per model:
    - average latency
    - SLA violations
    - fallback usage
    - drift adjustment rate
    - confidence trend
    
    Returns:
    - model_name: Model identifier
    - usage_count: Total number of requests
    - avg_latency_ms: Average request latency
    - fallback_count: Number of fallback events
    - drift_adjustments: Number of drift adjustments
    - drift_adjustment_rate: Rate of drift adjustments (0.0-1.0)
    - last_used_at: ISO timestamp of last usage
    - sla_violations: Number of SLA violations (latency > threshold)
    - confidence_trend: Confidence trend information
    """
    return {
        "models": get_model_health_summary()
    }

@router.post("/api/v1/ai/governance/model-hot-reload")
def model_hot_reload(
    identity: dict = Depends(get_current_user_or_service),
    request: Request = None,
    model_name: str = Query(..., description="Model name to set as default"),
    org_id: str = Query(None, description="Optional org_id for org-specific model")
):
    """
    Hot-reload model configuration without service restart.
    Updates are persisted to database for cluster-wide consistency.
    
    Query Parameters:
    - model_name: Model name to set
    - org_id: Optional organization ID for org-specific model
    
    Returns:
    - Updated model configuration
    """
    requester_org_id = identity.get("org_id")
    correlation_id = request.headers.get("X-Request-ID") if request else None
    updated_by = identity.get("user_id") or identity.get("service_name")
    
    if org_id:
        # Set org-specific model
        if requester_org_id and requester_org_id != org_id:
            raise HTTPException(
                status_code=403,
                detail="Cannot set model for other organizations"
            )
        model_manager.set_org_model(
            org_id,
            model_name,
            enabled=True,
            updated_by=updated_by,
            correlation_id=correlation_id
        )
        return {
            "status": "success",
            "message": f"Model updated for organization {org_id} (cluster-wide)",
            "org_id": org_id,
            "model_name": model_name,
            "correlation_id": correlation_id
        }
    else:
        # Set default model (requires admin privileges - can be enhanced)
        model_manager.set_default_model(
            model_name,
            updated_by=updated_by,
            correlation_id=correlation_id
        )
        return {
            "status": "success",
            "message": "Default model updated (cluster-wide)",
            "model_name": model_name,
            "correlation_id": correlation_id
        }

@router.get("/api/v1/ai/governance/model-config")
def get_model_config(
    identity: dict = Depends(get_current_user_or_service)
):
    """
    Get current model configuration.
    
    Returns:
    - Current model configuration including default and org-specific models
    """
    org_id = identity.get("org_id")
    configs = model_manager.get_all_configs()
    
    # Filter org-specific configs if user is not admin
    if org_id:
        org_config = model_manager.get_org_model(org_id)
        return {
            "default_model": configs["default_model"],
            "org_model": org_config,
            "org_id": org_id
        }
    else:
        return configs
