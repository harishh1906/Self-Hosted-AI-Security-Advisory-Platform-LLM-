"""
Model Health Tracking
Tracks real-time health metrics per model for production monitoring.
"""
import logging
import time
import statistics
from threading import RLock
from typing import Dict, Optional, List
from collections import deque
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# SLA threshold for latency (milliseconds) — imported from central config
from app.config import SLA_LATENCY_THRESHOLD_MS
SLA_LATENCY_THRESHOLD = SLA_LATENCY_THRESHOLD_MS

class ModelHealthTracker:
    """Thread-safe model health tracker."""
    
    def __init__(self, max_samples: int = 1000):
        self._lock = RLock()  # RLock: get_all_models_health calls get_model_health inside the same lock
        self._max_samples = max_samples
        
        # Per-model tracking
        # Structure: model_name -> {
        #   "latency_samples": deque,
        #   "fallback_count": int,
        #   "drift_adjustment_count": int,
        #   "sla_violation_count": int,
        #   "total_requests": int,
        #   "last_used": datetime
        # }
        self._model_metrics: Dict[str, Dict] = {}
    
    def record_request(
        self,
        model_name: str,
        latency_ms: float,
        used_fallback: bool = False,
        drift_adjusted: bool = False
    ):
        """Record a request for a model."""
        with self._lock:
            if model_name not in self._model_metrics:
                self._model_metrics[model_name] = {
                    "latency_samples": deque(maxlen=self._max_samples),
                    "fallback_count": 0,
                    "drift_adjustment_count": 0,
                    "sla_violation_count": 0,
                    "total_requests": 0,
                    "last_used": datetime.now(timezone.utc)
                }
            
            metrics = self._model_metrics[model_name]
            metrics["latency_samples"].append(latency_ms)
            metrics["total_requests"] += 1
            metrics["last_used"] = datetime.now(timezone.utc)
            
            if used_fallback:
                metrics["fallback_count"] += 1
            
            if drift_adjusted:
                metrics["drift_adjustment_count"] += 1
            
            # Track SLA violations
            if latency_ms > SLA_LATENCY_THRESHOLD:
                metrics["sla_violation_count"] += 1
    
    def get_model_health(self, model_name: str) -> Optional[Dict]:
        """Get health metrics for a specific model."""
        with self._lock:
            if model_name not in self._model_metrics:
                return None
            
            metrics = self._model_metrics[model_name]
            latency_samples = list(metrics["latency_samples"])
            
            avg_latency = statistics.mean(latency_samples) if latency_samples else 0.0
            
            total_requests = metrics["total_requests"]
            fallback_rate = (metrics["fallback_count"] / total_requests) if total_requests > 0 else 0.0
            drift_adjustment_rate = (metrics["drift_adjustment_count"] / total_requests) if total_requests > 0 else 0.0
            
            # Check if model is "loaded" (has been used recently)
            last_used = metrics["last_used"]
            is_loaded = (datetime.now(timezone.utc) - last_used).total_seconds() < 3600  # Used in last hour
            
            return {
                "model_name": model_name,
                "is_loaded": is_loaded,
                "avg_latency_ms": round(avg_latency, 2),
                "fallback_count": metrics["fallback_count"],
                "fallback_rate": round(fallback_rate, 4),
                "drift_adjustment_rate": round(drift_adjustment_rate, 4),
                "drift_adjustment_count": metrics.get("drift_adjustment_count", 0),
                "sla_violation_count": metrics.get("sla_violation_count", 0),
                "total_requests": total_requests,
                "last_used": last_used.isoformat() if last_used else None
            }
    
    def get_all_models_health(self) -> List[Dict]:
        """Get health metrics for all tracked models."""
        with self._lock:
            health_list = []
            for model_name in self._model_metrics.keys():
                health = self.get_model_health(model_name)
                if health:
                    health_list.append(health)
            return health_list
    
    def is_model_healthy(self, model_name: str) -> bool:
        """Check if model meets SLA (latency < threshold)."""
        health = self.get_model_health(model_name)
        if not health:
            return True  # Unknown models considered healthy
        
        return health["avg_latency_ms"] < SLA_LATENCY_THRESHOLD

# Global model health tracker instance
model_health_tracker = ModelHealthTracker()

def get_model_health_summary() -> List[Dict]:
    """
    Get comprehensive real-time model health summary for control plane.
    
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
    from app.performance_intelligence import performance_intelligence
    
    models_health = model_health_tracker.get_all_models_health()
    summary_list = []
    
    for health in models_health:
        model_name = health["model_name"]
        
        # Get confidence trend
        confidence_trend = performance_intelligence.get_confidence_trend(model_name)
        confidence_trend_data = None
        if confidence_trend:
            confidence_trend_data = {
                "recent_avg": confidence_trend["recent_avg"],
                "older_avg": confidence_trend["older_avg"],
                "drop_percent": confidence_trend["drop_percent"],
                "is_declining": confidence_trend["is_declining"],
                "sample_count": confidence_trend["sample_count"]
            }
        
        # Extract all metrics from health data
        usage_count = health.get("total_requests", 0)
        avg_latency_ms = health.get("avg_latency_ms", 0.0)
        fallback_count = health.get("fallback_count", 0)
        drift_adjustments = health.get("drift_adjustment_count", 0)
        drift_adjustment_rate = health.get("drift_adjustment_rate", 0.0)
        sla_violations = health.get("sla_violation_count", 0)
        last_used_at = health.get("last_used")
        
        summary_list.append({
            "model_name": model_name,
            "usage_count": usage_count,
            "avg_latency_ms": round(avg_latency_ms, 2),
            "fallback_count": fallback_count,
            "drift_adjustments": drift_adjustments,
            "drift_adjustment_rate": round(drift_adjustment_rate, 4),
            "last_used_at": last_used_at,
            "sla_violations": sla_violations,
            "confidence_trend": confidence_trend_data
        })
    
    return summary_list
