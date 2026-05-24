"""
AI Cost and Performance Analytics Service
Tracks usage, cost, and performance metrics per policy configuration.
"""
import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, extract
from app.db.models import AICostAnalytics
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

# Cost estimation (per 1M tokens) - adjust based on your model pricing
# Using approximate Gemma 4 e2b pricing as reference (token-based estimation)
COST_PER_MILLION_INPUT_TOKENS = 0.10  # $0.10 per 1M input tokens
COST_PER_MILLION_OUTPUT_TOKENS = 0.30  # $0.30 per 1M output tokens

def estimate_cost(input_tokens: Optional[int], output_tokens: Optional[int]) -> float:
    """
    Estimate cost in USD based on token usage.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    
    Returns:
        Estimated cost in USD
    """
    if not input_tokens:
        input_tokens = 0
    if not output_tokens:
        output_tokens = 0
    
    input_cost = (input_tokens / 1_000_000) * COST_PER_MILLION_INPUT_TOKENS
    output_cost = (output_tokens / 1_000_000) * COST_PER_MILLION_OUTPUT_TOKENS
    
    return round(input_cost + output_cost, 6)

def record_analytics(
    org_id: str,
    endpoint: str,
    policy_id: Optional[int],
    policy_risk_tolerance: Optional[str],
    policy_verbosity: Optional[str],
    policy_compliance_mode: Optional[str],
    tokens_used: int,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    latency_ms: float,
    llm_latency_ms: Optional[float],
    success: str = "success",
    error_type: Optional[str] = None,
    correlation_id: Optional[str] = None,
    model_name: Optional[str] = None
):
    """
    Record analytics for a single request.
    
    Args:
        org_id: Organization ID
        endpoint: Endpoint name (e.g., "analyze")
        policy_id: Policy profile ID
        policy_risk_tolerance: Policy risk tolerance setting
        policy_verbosity: Policy verbosity setting
        policy_compliance_mode: Policy compliance mode
        tokens_used: Total tokens used
        input_tokens: Input tokens
        output_tokens: Output tokens
        latency_ms: Total request latency in milliseconds
        llm_latency_ms: LLM-only latency in milliseconds
        success: Request status ("success", "failure", "error")
        error_type: Error classification if failed
        correlation_id: Request correlation ID
    """
    db: Session = SessionLocal()
    try:
        estimated_cost = estimate_cost(input_tokens, output_tokens)
        
        analytics = AICostAnalytics(
            org_id=org_id,
            endpoint=endpoint,
            policy_id=policy_id,
            policy_risk_tolerance=policy_risk_tolerance,
            policy_verbosity=policy_verbosity,
            policy_compliance_mode=policy_compliance_mode,
            tokens_used=tokens_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name=model_name,
            estimated_cost_usd=estimated_cost,
            latency_ms=latency_ms,
            llm_latency_ms=llm_latency_ms,
            success=success,
            error_type=error_type,
            correlation_id=correlation_id
        )
        
        db.add(analytics)
        db.commit()
        
    except Exception as e:
        logger.error(
            f"Failed to record analytics: {e}",
            extra={
                "org_id": org_id,
                "endpoint": endpoint,
                "correlation_id": correlation_id
            },
            exc_info=True
        )
        db.rollback()
    finally:
        db.close()

def get_policy_cost_summary(
    org_id: str,
    endpoint: str = "analyze",
    month: Optional[int] = None,
    year: Optional[int] = None
) -> List[Dict]:
    """
    Get monthly cost summary grouped by policy configuration.
    
    Args:
        org_id: Organization ID
        endpoint: Endpoint name (default: "analyze")
        month: Month number (1-12), defaults to current month
        year: Year, defaults to current year
    
    Returns:
        List of summaries per policy configuration
    """
    db: Session = SessionLocal()
    try:
        if not month or not year:
            now = datetime.now(timezone.utc)
            month = month or now.month
            year = year or now.year
        
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Query aggregated by policy configuration
        results = db.query(
            AICostAnalytics.policy_id,
            AICostAnalytics.policy_risk_tolerance,
            AICostAnalytics.policy_verbosity,
            AICostAnalytics.policy_compliance_mode,
            func.sum(AICostAnalytics.tokens_used).label('total_tokens'),
            func.sum(AICostAnalytics.input_tokens).label('total_input_tokens'),
            func.sum(AICostAnalytics.output_tokens).label('total_output_tokens'),
            func.sum(AICostAnalytics.estimated_cost_usd).label('total_cost_usd'),
            func.count(AICostAnalytics.id).label('request_count')
        ).filter(
            and_(
                AICostAnalytics.org_id == org_id,
                AICostAnalytics.endpoint == endpoint,
                AICostAnalytics.created_at >= start_date,
                AICostAnalytics.created_at < end_date
            )
        ).group_by(
            AICostAnalytics.policy_id,
            AICostAnalytics.policy_risk_tolerance,
            AICostAnalytics.policy_verbosity,
            AICostAnalytics.policy_compliance_mode
        ).all()
        
        summaries = []
        for row in results:
            summaries.append({
                "policy_id": row.policy_id,
                "policy_risk_tolerance": row.policy_risk_tolerance,
                "policy_verbosity": row.policy_verbosity,
                "policy_compliance_mode": row.policy_compliance_mode,
                "total_tokens": int(row.total_tokens or 0),
                "total_input_tokens": int(row.total_input_tokens or 0),
                "total_output_tokens": int(row.total_output_tokens or 0),
                "total_cost_usd": float(row.total_cost_usd or 0.0),
                "request_count": int(row.request_count or 0),
                "avg_tokens_per_request": int((row.total_tokens or 0) / row.request_count) if row.request_count > 0 else 0,
                "avg_cost_per_request_usd": float((row.total_cost_usd or 0.0) / row.request_count) if row.request_count > 0 else 0.0
            })
        
        return summaries
        
    except Exception as e:
        logger.error(f"Failed to get cost summary: {e}", exc_info=True)
        return []
    finally:
        db.close()

def get_policy_latency_summary(
    org_id: str,
    endpoint: str = "analyze",
    month: Optional[int] = None,
    year: Optional[int] = None
) -> List[Dict]:
    """
    Get latency statistics grouped by policy configuration.
    
    Args:
        org_id: Organization ID
        endpoint: Endpoint name (default: "analyze")
        month: Month number (1-12), defaults to current month
        year: Year, defaults to current year
    
    Returns:
        List of latency summaries per policy configuration
    """
    db: Session = SessionLocal()
    try:
        if not month or not year:
            now = datetime.now(timezone.utc)
            month = month or now.month
            year = year or now.year
        
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Query aggregated by policy configuration
        results = db.query(
            AICostAnalytics.policy_id,
            AICostAnalytics.policy_risk_tolerance,
            AICostAnalytics.policy_verbosity,
            AICostAnalytics.policy_compliance_mode,
            func.avg(AICostAnalytics.latency_ms).label('avg_latency_ms'),
            func.avg(AICostAnalytics.llm_latency_ms).label('avg_llm_latency_ms'),
            func.min(AICostAnalytics.latency_ms).label('min_latency_ms'),
            func.max(AICostAnalytics.latency_ms).label('max_latency_ms'),
            func.count(AICostAnalytics.id).label('request_count')
        ).filter(
            and_(
                AICostAnalytics.org_id == org_id,
                AICostAnalytics.endpoint == endpoint,
                AICostAnalytics.created_at >= start_date,
                AICostAnalytics.created_at < end_date
            )
        ).group_by(
            AICostAnalytics.policy_id,
            AICostAnalytics.policy_risk_tolerance,
            AICostAnalytics.policy_verbosity,
            AICostAnalytics.policy_compliance_mode
        ).all()
        
        summaries = []
        for row in results:
            summaries.append({
                "policy_id": row.policy_id,
                "policy_risk_tolerance": row.policy_risk_tolerance,
                "policy_verbosity": row.policy_verbosity,
                "policy_compliance_mode": row.policy_compliance_mode,
                "avg_latency_ms": float(row.avg_latency_ms or 0.0),
                "avg_llm_latency_ms": float(row.avg_llm_latency_ms or 0.0),
                "min_latency_ms": float(row.min_latency_ms or 0.0),
                "max_latency_ms": float(row.max_latency_ms or 0.0),
                "request_count": int(row.request_count or 0)
            })
        
        return summaries
        
    except Exception as e:
        logger.error(f"Failed to get latency summary: {e}", exc_info=True)
        return []
    finally:
        db.close()

def get_policy_success_summary(
    org_id: str,
    endpoint: str = "analyze",
    month: Optional[int] = None,
    year: Optional[int] = None
) -> List[Dict]:
    """
    Get success/failure statistics grouped by policy configuration.
    
    Args:
        org_id: Organization ID
        endpoint: Endpoint name (default: "analyze")
        month: Month number (1-12), defaults to current month
        year: Year, defaults to current year
    
    Returns:
        List of success summaries per policy configuration
    """
    db: Session = SessionLocal()
    try:
        if not month or not year:
            now = datetime.now(timezone.utc)
            month = month or now.month
            year = year or now.year
        
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)
        
        # Query aggregated by policy configuration and success status
        results = db.query(
            AICostAnalytics.policy_id,
            AICostAnalytics.policy_risk_tolerance,
            AICostAnalytics.policy_verbosity,
            AICostAnalytics.policy_compliance_mode,
            AICostAnalytics.success,
            func.count(AICostAnalytics.id).label('count')
        ).filter(
            and_(
                AICostAnalytics.org_id == org_id,
                AICostAnalytics.endpoint == endpoint,
                AICostAnalytics.created_at >= start_date,
                AICostAnalytics.created_at < end_date
            )
        ).group_by(
            AICostAnalytics.policy_id,
            AICostAnalytics.policy_risk_tolerance,
            AICostAnalytics.policy_verbosity,
            AICostAnalytics.policy_compliance_mode,
            AICostAnalytics.success
        ).all()
        
        # Group by policy configuration
        policy_stats = {}
        for row in results:
            key = (row.policy_id, row.policy_risk_tolerance, row.policy_verbosity, row.policy_compliance_mode)
            if key not in policy_stats:
                policy_stats[key] = {
                    "policy_id": row.policy_id,
                    "policy_risk_tolerance": row.policy_risk_tolerance,
                    "policy_verbosity": row.policy_verbosity,
                    "policy_compliance_mode": row.policy_compliance_mode,
                    "total_requests": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "error_count": 0
                }
            
            policy_stats[key]["total_requests"] += row.count
            if row.success == "success":
                policy_stats[key]["success_count"] += row.count
            elif row.success == "failure":
                policy_stats[key]["failure_count"] += row.count
            else:
                policy_stats[key]["error_count"] += row.count
        
        summaries = []
        for stats in policy_stats.values():
            total = stats["total_requests"]
            summaries.append({
                "policy_id": stats["policy_id"],
                "policy_risk_tolerance": stats["policy_risk_tolerance"],
                "policy_verbosity": stats["policy_verbosity"],
                "policy_compliance_mode": stats["policy_compliance_mode"],
                "total_requests": total,
                "success_count": stats["success_count"],
                "failure_count": stats["failure_count"],
                "error_count": stats["error_count"],
                "success_rate": round((stats["success_count"] / total * 100) if total > 0 else 0.0, 2),
                "failure_rate": round((stats["failure_count"] / total * 100) if total > 0 else 0.0, 2),
                "error_rate": round((stats["error_count"] / total * 100) if total > 0 else 0.0, 2)
            })
        
        return summaries
        
    except Exception as e:
        logger.error(f"Failed to get success summary: {e}", exc_info=True)
        return []
    finally:
        db.close()

