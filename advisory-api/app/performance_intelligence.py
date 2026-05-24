"""
Performance Intelligence and Feedback Loops
Continuously evaluates model performance and provides optimization insights.
"""
import logging
import statistics
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, cast, Integer, Float
from sqlalchemy.dialects.postgresql import JSONB
from app.db.models import AICostAnalytics, AuditLog, AIOutputBaseline
from app.db.database import SessionLocal
from app.model_health import model_health_tracker

logger = logging.getLogger(__name__)

# Self-healing thresholds
CONFIDENCE_DROP_THRESHOLD = 0.1  # 10% drop triggers self-healing
CONFIDENCE_DROP_WINDOW = 10  # Check last 10 requests
SEVERITY_SENSITIVITY_REDUCTION = 0.1  # Reduce severity sensitivity by 10%

class PerformanceIntelligence:
    """Tracks model performance trends and provides optimization insights."""
    
    def __init__(self):
        self._confidence_history: Dict[str, List[float]] = {}  # model_name -> [confidence values]
        self._max_history = 100  # Keep last 100 confidence values per model
    
    def record_confidence(self, model_name: str, confidence: float):
        """Record confidence value for trend analysis."""
        if model_name not in self._confidence_history:
            self._confidence_history[model_name] = []
        
        history = self._confidence_history[model_name]
        history.append(confidence)
        
        # Keep only recent history
        if len(history) > self._max_history:
            history.pop(0)
    
    def get_confidence_trend(self, model_name: str) -> Optional[Dict]:
        """Get confidence trend for a model."""
        if model_name not in self._confidence_history:
            return None
        
        history = self._confidence_history[model_name]
        if len(history) < 5:
            return None
        
        recent = history[-CONFIDENCE_DROP_WINDOW:]
        older = history[-CONFIDENCE_DROP_WINDOW*2:-CONFIDENCE_DROP_WINDOW] if len(history) >= CONFIDENCE_DROP_WINDOW*2 else history[:-CONFIDENCE_DROP_WINDOW]
        
        if not older:
            return None
        
        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)
        
        drop_percent = ((older_avg - recent_avg) / older_avg * 100) if older_avg > 0 else 0
        
        return {
            "recent_avg": round(recent_avg, 3),
            "older_avg": round(older_avg, 3),
            "drop_percent": round(drop_percent, 2),
            "is_declining": drop_percent > (CONFIDENCE_DROP_THRESHOLD * 100),
            "sample_count": len(history)
        }
    
    def should_trigger_self_healing(self, model_name: str) -> bool:
        """Check if self-healing should be triggered for a model."""
        trend = self.get_confidence_trend(model_name)
        if not trend:
            return False
        
        return trend["is_declining"] and trend["drop_percent"] > (CONFIDENCE_DROP_THRESHOLD * 100)

# Global performance intelligence instance
performance_intelligence = PerformanceIntelligence()

def get_optimization_insights() -> Dict:
    """
    Get comprehensive optimization insights including:
    - top_performing_models (from ai_cost_analytics - ranked by latency & success rate)
    - fallback_usage_stats (count + rate)
    - drift_adjustment_trends (30-day grouped counts)
    - policy_profile_effectiveness (avg confidence + latency per policy_id)
    """
    db: Session = SessionLocal()
    try:
        from datetime import timedelta
        # 1. Top performing models (from ai_cost_analytics - ranked by lowest latency & highest success rate)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        
        model_performance = db.query(
            AICostAnalytics.model_name,
            func.avg(AICostAnalytics.latency_ms).label('avg_latency'),
            func.count(AICostAnalytics.id).label('request_count'),
            func.avg(cast(AICostAnalytics.success == 'success', Integer)).label('success_rate')
        ).filter(
            and_(
                AICostAnalytics.created_at >= thirty_days_ago,
                AICostAnalytics.model_name.isnot(None)
            )
        ).group_by(
            AICostAnalytics.model_name
        ).having(
            func.count(AICostAnalytics.id) >= 10  # Minimum 10 requests
        ).all()
        
        top_performing_models = []
        for perf in model_performance:
            # Performance score: lower latency + higher success rate = better
            latency_score = max(0.0, 1.0 / (1.0 + float(perf.avg_latency or 0) / 1000.0))
            success_score = float(perf.success_rate or 0)
            performance_score = (latency_score * 0.6) + (success_score * 0.4)  # Weighted combination
            
            top_performing_models.append({
                "model_name": perf.model_name,
                "avg_latency_ms": round(float(perf.avg_latency or 0), 2),
                "success_rate": round(success_score, 4),
                "total_requests": perf.request_count,
                "performance_score": round(performance_score, 4),
                "rank": 0
            })
        
        # Sort by performance score (descending)
        top_performing_models.sort(key=lambda x: x["performance_score"], reverse=True)
        for idx, model in enumerate(top_performing_models[:10], start=1):
            model["rank"] = idx
        top_performing_models = top_performing_models[:10]
        
        # 2. Fallback usage stats (from audit logs)
        try:
            # Group fallbacks by model using DB aggregation
            jsonb_payload = cast(AuditLog.payload, JSONB)
            fallback_stats = db.query(
                jsonb_payload['actual_model_used'].astext.label('model_name'),
                func.count(AuditLog.id).label('fallback_count')
            ).filter(
                and_(
                    AuditLog.created_at >= thirty_days_ago,
                    jsonb_payload.has_key('model_selection'),
                    jsonb_payload['model_selection'].astext.cast(JSONB)['used_fallback'].astext == 'true'
                )
            ).group_by(
                jsonb_payload['actual_model_used'].astext
            ).all()
            
            fallback_logs = sum(s.fallback_count for s in fallback_stats)
            
            total_requests = db.query(AuditLog).filter(
                AuditLog.created_at >= thirty_days_ago,
                AuditLog.action == 'analyze_finding'
            ).count()
            
            fallback_rate_overall = (fallback_logs / total_requests) if total_requests > 0 else 0.0
            
            models_with_fallbacks = [
                {"model_name": s.model_name or "unknown", "fallback_count": s.fallback_count}
                for s in fallback_stats
            ]
        except Exception as e:
            logger.warning(f"Error calculating fallback stats: {e}")
            fallback_logs = 0
            total_requests = 0
            fallback_rate_overall = 0.0
            models_with_fallbacks = []
        
        fallback_usage_stats = {
            "total_fallbacks": fallback_logs,
            "total_requests": total_requests,
            "overall_fallback_rate": round(fallback_rate_overall, 4),
            "models_with_fallbacks": models_with_fallbacks
        }
        
        # 3. Drift adjustment trends (from audit logs)
        try:
            drift_stats = db.query(
                func.date(AuditLog.created_at).label('date'),
                func.count(AuditLog.id).label('count')
            ).filter(
                and_(
                    AuditLog.created_at >= thirty_days_ago,
                    cast(AuditLog.payload, JSONB).has_key('drift_status'),
                    (cast(AuditLog.payload, JSONB)['drift_status'].astext) == 'DRIFT_DETECTED'
                )
            ).group_by(
                func.date(AuditLog.created_at)
            ).all()
            
            drift_by_date = {str(s.date): s.count for s in drift_stats}
            total_drift = sum(s.count for s in drift_stats)
            
            drift_adjustment_trends = {
                "total_drift_events": total_drift,
                "events_by_date": drift_by_date,
                "avg_events_per_day": round(total_drift / 30.0, 2)
            }
        except Exception as e:
            logger.warning(f"Error calculating drift trends: {e}")
            drift_adjustment_trends = {"total_drift_events": 0, "events_by_date": {}, "avg_events_per_day": 0.0}
        
        # 4. Policy profile effectiveness (optimized grouped query)
        try:
            # Single query to get avg confidence per policy_id
            jsonb_payload = cast(AuditLog.payload, JSONB)
            confidence_stats = db.query(
                jsonb_payload['policy_id'].astext.label('policy_id'),
                func.avg(jsonb_payload['model_confidence'].astext.cast(Float)).label('avg_confidence')
            ).filter(
                and_(
                    AuditLog.created_at >= thirty_days_ago,
                    jsonb_payload.has_key('model_confidence')
                )
            ).group_by(
                jsonb_payload['policy_id'].astext
            ).all()
            
            confidence_map = {str(s.policy_id): s.avg_confidence for s in confidence_stats}
            
            # Get policy usage stats from analytics
            policy_usage = db.query(
                AICostAnalytics.policy_id,
                func.avg(AICostAnalytics.latency_ms).label('avg_latency'),
                func.count(AICostAnalytics.id).label('request_count')
            ).filter(
                AICostAnalytics.created_at >= thirty_days_ago,
                AICostAnalytics.policy_id.isnot(None)
            ).group_by(
                AICostAnalytics.policy_id
            ).all()
            
            policy_profile_effectiveness = [
                {
                    "policy_id": stat.policy_id,
                    "avg_latency_ms": round(float(stat.avg_latency or 0), 2),
                    "request_count": stat.request_count,
                    "avg_confidence": round(confidence_map.get(str(stat.policy_id), 0), 3)
                }
                for stat in policy_usage
            ]
            
            policy_profile_effectiveness.sort(key=lambda x: x["avg_confidence"], reverse=True)
        except Exception as e:
            logger.warning(f"Error calculating policy effectiveness: {e}")
            policy_profile_effectiveness = []
        
        # 5. Model selection decision chain per request (from audit logs - with error handling)
        try:
            recent_requests = db.query(AuditLog).filter(
                and_(
                    AuditLog.created_at >= thirty_days_ago,
                    cast(AuditLog.payload, JSONB).has_key('model_selection')
                )
            ).order_by(AuditLog.created_at.desc()).limit(100).all()
        except Exception as e:
            logger.warning(f"Error querying model selection chains: {e}")
            recent_requests = []
        
        model_selection_chains = []
        for log in recent_requests:
            model_selection = log.payload.get('model_selection', {})
            decision_reason = log.payload.get('decision_reason')
            applied_policy_params = log.payload.get('applied_policy_params', {})
            
            # Build comprehensive decision chain
            chain = {
                "correlation_id": log.payload.get('correlation_id') if log.payload else None,
                "org_id": log.org_id,
                "policy_id": log.payload.get('policy_id') if log.payload else None,
                "timestamp": log.created_at.isoformat(),
                "selected_model": model_selection.get("selected_model"),
                "primary_model": model_selection.get("primary_model"),
                "fallback_model": model_selection.get("fallback_model"),
                "actual_model_used": log.payload.get('actual_model_used') if log.payload else model_selection.get("selected_model"),
                "used_fallback": model_selection.get("used_fallback", False),
                "force_model": model_selection.get("force_model"),
                "model_override": model_selection.get("model_override"),
                "decision_reason": decision_reason,
                "applied_policy_params": applied_policy_params,
                "response_time_ms": log.payload.get('response_time_ms') if log.payload else None,
                "model_confidence": log.payload.get('model_confidence') if log.payload else None
            }
            model_selection_chains.append(chain)
        
        return {
            "top_performing_models": top_performing_models,
            "fallback_usage_stats": fallback_usage_stats,
            "drift_adjustment_trends": drift_adjustment_trends,
            "policy_profile_effectiveness": policy_profile_effectiveness,
            "model_selection_decision_chains": model_selection_chains
        }
    except Exception as e:
        logger.error(f"Failed to get optimization insights: {e}", exc_info=True)
        return {
            "top_performing_models": [],
            "fallback_usage_stats": {"total_fallbacks": 0, "total_requests": 0, "overall_fallback_rate": 0.0, "models_with_fallbacks": []},
            "drift_adjustment_trends": {"total_drift_events": 0, "events_by_date": {}, "avg_events_per_day": 0.0},
            "policy_profile_effectiveness": [],
            "model_selection_decision_chains": []
        }
    finally:
        db.close()

