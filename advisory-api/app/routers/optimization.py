import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from app.auth.dependencies import get_current_user_or_service
from app.performance_intelligence import get_optimization_insights
from app.policy_effectiveness import get_policy_effectiveness
from app.optimization.engine import get_optimization_recommendations, get_active_models

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Optimization & SLA Tuning"])

@router.get("/internal/optimization-insights")
def get_optimization_insights_endpoint(identity: dict = Depends(get_current_user_or_service)):
    """
    Get optimization insights for production intelligence feedback loops.
    
    Returns:
    - top_performing_models: Models ranked by performance (latency, fallback rate)
    - fallback_usage_stats: Overall fallback statistics
    - drift_adjustment_trends: Drift detection trends over time
    - policy_profile_effectiveness: Policy configuration effectiveness metrics
    - model_selection_decision_chains: Model selection decision chain per request (last 100)
    
    Note: Does not affect advisory responses - internal intelligence only.
    """
    try:
        return get_optimization_insights()
    except Exception as e:
        logger.error(f"Error getting optimization insights: {e}", exc_info=True)
        # Graceful degradation - return empty structure
        return {
            "top_performing_models": [],
            "fallback_usage_stats": {
                "total_fallbacks": 0,
                "total_requests": 0,
                "overall_fallback_rate": 0.0,
                "models_with_fallbacks": []
            },
            "drift_adjustment_trends": {
                "total_drift_events": 0,
                "events_by_date": {},
                "avg_events_per_day": 0.0
            },
            "policy_profile_effectiveness": [],
            "model_selection_decision_chains": []
        }

@router.get("/internal/policy-effectiveness")
def get_policy_effectiveness_endpoint(identity: dict = Depends(get_current_user_or_service)):
    """
    Get policy effectiveness metrics.
    
    Returns:
    - policy_id: Policy profile ID
    - avg_confidence: Average confidence score
    - avg_latency: Average request latency
    - drift_frequency: Frequency of drift detection (0.0-1.0)
    - tenant_rating_average: Average tenant rating (1.0-5.0)
    """
    return {
        "policies": get_policy_effectiveness()
    }

@router.get("/api/v1/ai/governance/model-optimization-recommendations")
def model_optimization_recommendations(
    identity: dict = Depends(get_current_user_or_service),
    policy_id: int = Query(None, description="Optional policy ID to filter by specific policy"),
    request: Request = None
):
    """
    Get AI model optimization recommendations per organization and policy profile.
    
    Analyzes last 30 days of usage data and recommends optimal models based on:
    - Cost optimization (if cost is high but latency acceptable)
    - Latency optimization (if latency is high)
    - Accuracy optimization (if drift is frequent)
    - Budget optimization (if budget utilization > 80%)
    
    Query Parameters:
    - policy_id: Optional policy ID to filter by specific policy
    
    Returns:
    - Recommended model per policy configuration
    - Average cost, latency, drift frequency, and budget utilization
    """
    org_id = identity.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    # Generate correlation ID for promotion logging
    correlation_id = request.headers.get("X-Request-ID") if request else None
    
    recommendations = get_optimization_recommendations(org_id, policy_id, correlation_id)
    
    # If single policy requested, return single recommendation object (matching example format)
    if policy_id is not None and len(recommendations) == 1:
        return recommendations[0]
    
    # Otherwise return list format
    return {
        "org_id": org_id,
        "recommendations": recommendations
    }

@router.get("/api/v1/ai/governance/active-models")
def active_models(
    identity: dict = Depends(get_current_user_or_service),
    policy_id: int = Query(None, description="Optional policy ID to filter by specific policy")
):
    """
    Get currently active models per organization and policy profile.
    
    Shows which models are currently in use after automatic promotion.
    
    Query Parameters:
    - policy_id: Optional policy ID to filter by specific policy
    
    Returns:
    - Active model per policy configuration
    - Promotion reason, confidence, and last promotion timestamp
    """
    org_id = identity.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    active_models_list = get_active_models(org_id, policy_id)
    
    # If single policy requested, return single active model object (matching example format)
    if policy_id is not None and len(active_models_list) == 1:
        return active_models_list[0]
    
    # Otherwise return list format
    return {
        "org_id": org_id,
        "active_models": active_models_list
    }
