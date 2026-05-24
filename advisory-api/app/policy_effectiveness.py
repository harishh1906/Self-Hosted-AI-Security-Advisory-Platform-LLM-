"""
Policy Effectiveness Analysis
Tracks and analyzes policy performance metrics.
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, cast, Integer, Float
from app.db.models import AICostAnalytics, AuditLog, AIPolicyProfile
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

def get_policy_effectiveness() -> List[Dict]:
    """
    Get policy effectiveness metrics including:
    - policy_id
    - avg_confidence
    - avg_latency
    - drift_frequency
    - tenant_rating_average
    """
    db: Session = SessionLocal()
    try:
        # Get all policies
        policies = db.query(AIPolicyProfile).all()
        
        effectiveness_list = []
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        for policy in policies:
            policy_id = policy.id
            
            # Get analytics for this policy
            analytics = db.query(
                func.avg(AICostAnalytics.latency_ms).label('avg_latency'),
                func.count(AICostAnalytics.id).label('request_count')
            ).filter(
                and_(
                    AICostAnalytics.policy_id == policy_id,
                    AICostAnalytics.created_at >= thirty_days_ago
                )
            ).first()
            
            # Get average confidence from audit logs
            confidence_logs = db.query(
                func.avg(cast(AuditLog.payload['confidence'].astext, Float)).label('avg_confidence')
            ).filter(
                and_(
                    AuditLog.policy_id == policy_id,
                    AuditLog.created_at >= thirty_days_ago,
                    AuditLog.action == 'analyze_finding'
                )
            ).first()
            
            # Get drift frequency (drift events / total requests)
            total_requests = analytics.request_count if analytics else 0
            drift_events = db.query(func.count(AuditLog.id)).filter(
                and_(
                    AuditLog.policy_id == policy_id,
                    AuditLog.created_at >= thirty_days_ago,
                    AuditLog.payload['drift_status'].astext == 'DRIFT_DETECTED'
                )
            ).scalar() or 0
            
            drift_frequency = (drift_events / total_requests) if total_requests > 0 else 0.0
            
            # Get tenant rating average
            tenant_ratings = db.query(
                func.avg(AICostAnalytics.tenant_rating).label('avg_rating')
            ).filter(
                and_(
                    AICostAnalytics.policy_id == policy_id,
                    AICostAnalytics.created_at >= thirty_days_ago,
                    AICostAnalytics.tenant_rating.isnot(None)
                )
            ).first()
            
            effectiveness_list.append({
                "policy_id": policy_id,
                "org_id": policy.org_id,
                "avg_confidence": round(float(confidence_logs.avg_confidence), 3) if confidence_logs and confidence_logs.avg_confidence else None,
                "avg_latency": round(float(analytics.avg_latency), 2) if analytics and analytics.avg_latency else None,
                "drift_frequency": round(drift_frequency, 4),
                "tenant_rating_average": round(float(tenant_ratings.avg_rating), 2) if tenant_ratings and tenant_ratings.avg_rating else None,
                "request_count": total_requests
            })
        
        return effectiveness_list
    except Exception as e:
        logger.error(f"Failed to get policy effectiveness: {e}", exc_info=True)
        return []
    finally:
        db.close()

