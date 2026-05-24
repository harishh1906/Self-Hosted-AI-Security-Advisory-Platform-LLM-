"""
Metrics Collection (Hooks for future Prometheus integration)
Tracks counters and latency percentiles.
"""
import math
import time
from threading import Lock
from typing import Dict, List
from collections import deque

class Metrics:
    """Thread-safe metrics counter with latency tracking."""

    def __init__(self, max_latency_samples: int = 1000):
        self._lock = Lock()
        self._counters: Dict[str, int] = {
            "requests_total": 0,
            "success_count": 0,
            "failures_total": 0,
            "degraded_total": 0,   # RAG unavailable
            "fallback_count": 0,   # LLM model fallback
            "self_healing_count": 0,  # verbosity/severity degradation triggered
            "drift_count": 0,      # AI output drift detected
            "tokens_total": 0,     # Total tokens consumed
        }
        self._latency_samples: deque = deque(maxlen=max_latency_samples)
        self._start_time = time.time()

    def increment(self, metric_name: str, value: int = 1):
        """Increment a named counter."""
        with self._lock:
            if metric_name in self._counters:
                self._counters[metric_name] += value
            else:
                self._counters[metric_name] = value

    def record_tokens(self, tokens: int):
        """Record token usage."""
        self.increment("tokens_total", tokens)

    def record_latency(self, latency_ms: float):
        """Record a latency sample (total request latency)."""
        with self._lock:
            self._latency_samples.append(latency_ms)

    def _percentile(self, sorted_samples: List[float], p: float) -> float:
        """Nearest-rank percentile (same method used by Prometheus/Grafana)."""
        n = len(sorted_samples)
        if n == 0:
            return 0.0
        idx = max(0, min(n - 1, math.ceil(p / 100.0 * n) - 1))
        return sorted_samples[idx]

    def get_metrics(self) -> Dict:
        """Return all counters plus latency percentiles and throughput."""
        with self._lock:
            samples = sorted(self._latency_samples)
            result = self._counters.copy()
            result["latency_sample_count"] = len(samples)

            # Calculate throughput (RPS)
            uptime = time.time() - self._start_time
            if uptime > 0:
                result["requests_per_second"] = round(result["requests_total"] / uptime, 2)
            else:
                result["requests_per_second"] = 0.0

            if samples:
                result["p50_latency_ms"] = self._percentile(samples, 50)
                result["p95_latency_ms"] = self._percentile(samples, 95)
                result["p99_latency_ms"] = self._percentile(samples, 99)
                result["min_latency_ms"] = samples[0]
                result["max_latency_ms"] = samples[-1]
                result["avg_latency_ms"] = sum(samples) / len(samples)
            else:
                result["p50_latency_ms"] = 0.0
                result["p95_latency_ms"] = 0.0
                result["p99_latency_ms"] = 0.0
                result["min_latency_ms"] = 0.0
                result["max_latency_ms"] = 0.0
                result["avg_latency_ms"] = 0.0

            return result

    def reset(self):
        """Reset all metrics (for testing)."""
        with self._lock:
            for key in self._counters:
                self._counters[key] = 0
            self._latency_samples.clear()

# Global metrics instance
metrics = Metrics()
