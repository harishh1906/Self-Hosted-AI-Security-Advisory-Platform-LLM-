import logging
import asyncio
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from app.auth.dependencies import get_current_user_or_service
from app.metrics import metrics
from app.model_health import get_model_health_summary
from app.analytics.service import (
    get_policy_cost_summary,
    get_policy_latency_summary,
    get_policy_success_summary
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics & Intelligence"])

@router.get("/internal/stream")
async def sse_stream(request: Request, token: str = Query(..., description="JWT bearer token (EventSource can't send headers)")):
    """
    Server-Sent Events stream — one persistent connection for real-time dashboard metrics.
    Pushes metrics + model health every 15s. Only fast in-memory data (no DB queries).
    Auth: pass JWT as ?token=<jwt> since EventSource API does not support custom headers.
    """
    # Validate token from query param (EventSource can't send Authorization header)
    from app.auth.jwt import decode_access_token
    try:
        decode_access_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    async def event_generator():
        try:
            while True:
                # 1. Quick in-memory metrics
                metrics_data = metrics.get_metrics()

                # 2. Model health — pure in-memory, runs in executor to avoid blocking event loop
                try:
                    models_data = await asyncio.get_event_loop().run_in_executor(
                        None, get_model_health_summary
                    )
                except Exception as e:
                    logger.warning(f"SSE model health check failed: {e}")
                    models_data = []

                payload = {
                    "metrics": {
                        "requests_total": metrics_data.get("requests_total", 0),
                        "success_count": metrics_data.get("success_count", 0),
                        "failures_total": metrics_data.get("failures_total", 0),
                        "degraded_total": metrics_data.get("degraded_total", 0),
                        "fallback_count": metrics_data.get("fallback_count", 0),
                        "self_healing_count": metrics_data.get("self_healing_count", 0),
                        "drift_count": metrics_data.get("drift_count", 0),
                        "tokens_total": metrics_data.get("tokens_total", 0),
                        "requests_per_second": metrics_data.get("requests_per_second", 0.0),
                        "p50_latency_ms": metrics_data.get("p50_latency_ms", 0.0),
                        "p95_latency_ms": metrics_data.get("p95_latency_ms", 0.0),
                        "p99_latency_ms": metrics_data.get("p99_latency_ms", 0.0),
                        "min_latency_ms": metrics_data.get("min_latency_ms", 0.0),
                        "max_latency_ms": metrics_data.get("max_latency_ms", 0.0),
                        "avg_latency_ms": metrics_data.get("avg_latency_ms", 0.0),
                        "latency_sample_count": metrics_data.get("latency_sample_count", 0),
                    },
                    "models": models_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                yield f"data: {json.dumps(payload)}\n\n"
                
                await asyncio.sleep(15)

        except asyncio.CancelledError:
            logger.info("SSE client disconnected")
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': 'Stream error'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # Critical: disables Nginx proxy buffering for SSE
        },
    )

@router.get("/internal/metrics")
def get_metrics(identity: dict = Depends(get_current_user_or_service)):
    """
    Internal metrics endpoint.
    Returns current metric counters including:
    - requests_total: Total number of requests
    - failures_total: Total number of failures
    - degraded_total: Total number of degraded requests
    - p95_latency: 95th percentile latency in milliseconds
    """
    metrics_dict = metrics.get_metrics()
    
    return {
        "requests_total": metrics_dict.get("requests_total", 0),
        "success_count": metrics_dict.get("success_count", 0),
        "failures_total": metrics_dict.get("failures_total", 0),
        "degraded_total": metrics_dict.get("degraded_total", 0),
        "fallback_count": metrics_dict.get("fallback_count", 0),
        "self_healing_count": metrics_dict.get("self_healing_count", 0),
        "drift_count": metrics_dict.get("drift_count", 0),
        "tokens_total": metrics_dict.get("tokens_total", 0),
        "requests_per_second": metrics_dict.get("requests_per_second", 0.0),
        # Latency — p95_latency kept for frontend backward-compat alias
        "p95_latency": metrics_dict.get("p95_latency_ms", 0.0),
        "p50_latency_ms": metrics_dict.get("p50_latency_ms", 0.0),
        "p95_latency_ms": metrics_dict.get("p95_latency_ms", 0.0),
        "p99_latency_ms": metrics_dict.get("p99_latency_ms", 0.0),
        "avg_latency_ms": metrics_dict.get("avg_latency_ms", 0.0),
        "min_latency_ms": metrics_dict.get("min_latency_ms", 0.0),
        "max_latency_ms": metrics_dict.get("max_latency_ms", 0.0),
        "latency_sample_count": metrics_dict.get("latency_sample_count", 0),
    }

@router.get("/api/v1/ai/governance/policy-cost-summary")
def policy_cost_summary(
    identity: dict = Depends(get_current_user_or_service),
    endpoint: str = Query("analyze", description="Endpoint name"),
    month: int = Query(None, ge=1, le=12, description="Month number (1-12)"),
    year: int = Query(None, ge=2020, description="Year")
):
    """
    Get monthly cost summary grouped by policy configuration.
    
    Query Parameters:
    - endpoint: Endpoint name (default: "analyze")
    - month: Month number (1-12), defaults to current month
    - year: Year, defaults to current year
    
    Returns:
    - Monthly tokens used per policy configuration
    - Cost estimates per policy configuration
    """
    org_id = identity.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    summaries = get_policy_cost_summary(org_id, endpoint, month, year)
    
    return {
        "org_id": org_id,
        "endpoint": endpoint,
        "month": month,
        "year": year,
        "summaries": summaries,
        "total_cost_usd": sum(s["total_cost_usd"] for s in summaries),
        "total_tokens": sum(s["total_tokens"] for s in summaries),
        "total_requests": sum(s["request_count"] for s in summaries)
    }

@router.get("/api/v1/ai/governance/policy-latency-summary")
def policy_latency_summary(
    identity: dict = Depends(get_current_user_or_service),
    endpoint: str = Query("analyze", description="Endpoint name"),
    month: int = Query(None, ge=1, le=12, description="Month number (1-12)"),
    year: int = Query(None, ge=2020, description="Year")
):
    """
    Get latency statistics grouped by policy configuration.
    
    Query Parameters:
    - endpoint: Endpoint name (default: "analyze")
    - month: Month number (1-12), defaults to current month
    - year: Year, defaults to current year
    
    Returns:
    - Latency statistics per policy configuration
    """
    org_id = identity.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    summaries = get_policy_latency_summary(org_id, endpoint, month, year)
    
    return {
        "org_id": org_id,
        "endpoint": endpoint,
        "month": month,
        "year": year,
        "summaries": summaries
    }

@router.get("/api/v1/ai/governance/policy-success-summary")
def policy_success_summary(
    identity: dict = Depends(get_current_user_or_service),
    endpoint: str = Query("analyze", description="Endpoint name"),
    month: int = Query(None, ge=1, le=12, description="Month number (1-12)"),
    year: int = Query(None, ge=2020, description="Year")
):
    """
    Get success/failure statistics grouped by policy configuration.
    
    Query Parameters:
    - endpoint: Endpoint name (default: "analyze")
    - month: Month number (1-12), defaults to current month
    - year: Year, defaults to current year
    
    Returns:
    - Success and failure statistics per policy configuration
    """
    org_id = identity.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="org_id required")
    
    summaries = get_policy_success_summary(org_id, endpoint, month, year)
    
    return {
        "org_id": org_id,
        "endpoint": endpoint,
        "month": month,
        "year": year,
        "summaries": summaries
    }
