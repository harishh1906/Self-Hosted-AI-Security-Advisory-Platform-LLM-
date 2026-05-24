"""
Circuit Breaker for Production Safety
Prevents cascading failures by entering degraded mode when failure rate exceeds threshold.
"""
import time
import logging
from threading import Lock
from typing import Dict, List
from enum import Enum

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit open, degraded mode
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """
    Circuit breaker that tracks failure rate over a time window.
    Enters degraded mode (skip RAG) when failure rate exceeds threshold.
    """
    
    def __init__(
        self,
        failure_threshold: float = 0.5,  # 50% failure rate
        time_window_seconds: int = 300,  # 5 minutes
        min_requests: int = 10  # Minimum requests before evaluating
    ):
        self.failure_threshold = failure_threshold
        self.time_window_seconds = time_window_seconds
        self.min_requests = min_requests
        
        self._lock = Lock()
        self._state = CircuitState.CLOSED
        self._request_history: List[Dict] = []  # List of {timestamp, success, failed}
        self._state_changes: List[Dict] = []  # Audit trail of state changes
    
    def record_request(self, success: bool, failed: bool):
        """Record a request outcome."""
        with self._lock:
            now = time.time()
            self._request_history.append({
                "timestamp": now,
                "success": success,
                "failed": failed
            })
            
            # Clean old history (outside time window)
            cutoff = now - self.time_window_seconds
            self._request_history = [
                r for r in self._request_history
                if r["timestamp"] > cutoff
            ]
            
            # Evaluate circuit state
            self._evaluate_state()
    
    def _evaluate_state(self):
        """Evaluate if circuit should change state."""
        if len(self._request_history) < self.min_requests:
            # Not enough data, stay in current state
            return
        
        # Calculate failure rate
        total = len(self._request_history)
        failures = sum(1 for r in self._request_history if r["failed"])
        failure_rate = failures / total if total > 0 else 0
        
        old_state = self._state
        
        if self._state == CircuitState.CLOSED:
            if failure_rate >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._log_state_change(old_state, self._state, failure_rate)
        elif self._state == CircuitState.OPEN:
            # Stay open for full time window, then try half-open
            if len(self._request_history) >= self.min_requests:
                # Check recent requests (last 10% of window)
                recent_cutoff = time.time() - (self.time_window_seconds * 0.1)
                recent = [r for r in self._request_history if r["timestamp"] > recent_cutoff]
                if len(recent) >= 3:  # At least 3 recent requests
                    recent_failures = sum(1 for r in recent if r["failed"])
                    recent_failure_rate = recent_failures / len(recent) if recent else 0
                    if recent_failure_rate < self.failure_threshold * 0.5:  # 50% of threshold
                        self._state = CircuitState.HALF_OPEN
                        self._log_state_change(old_state, self._state, recent_failure_rate)
        elif self._state == CircuitState.HALF_OPEN:
            # If recent requests are good, close circuit
            recent_cutoff = time.time() - (self.time_window_seconds * 0.1)
            recent = [r for r in self._request_history if r["timestamp"] > recent_cutoff]
            if len(recent) >= 5:
                recent_failures = sum(1 for r in recent if r["failed"])
                recent_failure_rate = recent_failures / len(recent) if recent else 0
                if recent_failure_rate < self.failure_threshold * 0.3:  # 30% of threshold
                    self._state = CircuitState.CLOSED
                    self._log_state_change(old_state, self._state, recent_failure_rate)
                elif recent_failure_rate >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._log_state_change(old_state, self._state, recent_failure_rate)
    
    def _log_state_change(self, old_state: CircuitState, new_state: CircuitState, failure_rate: float):
        """Log circuit breaker state changes."""
        change = {
            "timestamp": time.time(),
            "old_state": old_state.value,
            "new_state": new_state.value,
            "failure_rate": failure_rate,
            "request_count": len(self._request_history)
        }
        self._state_changes.append(change)
        
        logger.warning(
            f"Circuit breaker state changed: {old_state.value} -> {new_state.value}",
            extra={
                "circuit_breaker": {
                    "old_state": old_state.value,
                    "new_state": new_state.value,
                    "failure_rate": failure_rate,
                    "request_count": len(self._request_history)
                }
            }
        )
    
    def should_skip_rag(self) -> bool:
        """Check if RAG should be skipped (circuit open or half-open)."""
        with self._lock:
            return self._state in [CircuitState.OPEN, CircuitState.HALF_OPEN]
    
    def get_state(self) -> Dict:
        """Get current circuit breaker state and statistics."""
        with self._lock:
            total = len(self._request_history)
            failures = sum(1 for r in self._request_history if r["failed"])
            successes = sum(1 for r in self._request_history if r["success"])
            failure_rate = failures / total if total > 0 else 0
            
            return {
                "state": self._state.value,
                "failure_rate": failure_rate,
                "total_requests": total,
                "successes": successes,
                "failures": failures,
                "recent_state_changes": self._state_changes[-5:]  # Last 5 changes
            }
    
    def reset(self):
        """Reset circuit breaker (for testing)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._request_history = []
            self._state_changes = []

# Global circuit breaker instance
circuit_breaker = CircuitBreaker(
    failure_threshold=0.5,  # 50% failure rate
    time_window_seconds=300,  # 5 minutes
    min_requests=10  # Need at least 10 requests before evaluating
)

