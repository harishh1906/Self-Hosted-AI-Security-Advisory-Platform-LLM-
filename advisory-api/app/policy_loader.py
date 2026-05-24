"""
AI Policy Profile Loader with Caching
Loads tenant-specific AI policies with 5-minute TTL cache.
"""
import time
import logging
from typing import Dict, Optional
from threading import Lock
from sqlalchemy.orm import Session
from app.db.models import AIPolicyProfile
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)

# Default policy profile
DEFAULT_POLICY = {
    "risk_tolerance": "medium",
    "verbosity": "balanced",
    "compliance_mode": "none",
    "remediation_style": "practical"
}

class PolicyCache:
    """Thread-safe policy cache with TTL."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minutes
        self._lock = Lock()
        self._cache: Dict[str, Dict] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self.ttl_seconds = ttl_seconds
    
    def get(self, org_id: str) -> Optional[Dict]:
        """Get policy from cache if valid."""
        with self._lock:
            if org_id in self._cache:
                timestamp = self._cache_timestamps.get(org_id, 0)
                if time.time() - timestamp < self.ttl_seconds:
                    return self._cache[org_id]
                else:
                    # Expired, remove from cache
                    del self._cache[org_id]
                    del self._cache_timestamps[org_id]
            return None
    
    def set(self, org_id: str, policy: Dict):
        """Store policy in cache."""
        with self._lock:
            self._cache[org_id] = policy
            self._cache_timestamps[org_id] = time.time()
    
    def invalidate(self, org_id: str):
        """Invalidate cache for specific org."""
        with self._lock:
            if org_id in self._cache:
                del self._cache[org_id]
                del self._cache_timestamps[org_id]
    
    def clear(self):
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
            self._cache_timestamps.clear()

# Global cache instance
policy_cache = PolicyCache(ttl_seconds=300)

def load_policy(org_id: str) -> Dict:
    """
    Load AI policy profile for organization.
    Returns cached policy if available, otherwise loads from database.
    Falls back to default policy if none exists.
    """
    # Check cache first
    cached = policy_cache.get(org_id)
    if cached:
        logger.debug(f"Policy cache hit for org_id={org_id}")
        return cached
    
    # Load from database
    db: Session = SessionLocal()
    try:
        policy_record = db.query(AIPolicyProfile).filter(
            AIPolicyProfile.org_id == org_id
        ).first()
        
        if policy_record:
            policy = {
                "policy_id": policy_record.id,
                "org_id": policy_record.org_id,
                "risk_tolerance": policy_record.risk_tolerance,
                "verbosity": policy_record.verbosity,
                "compliance_mode": policy_record.compliance_mode,
                "remediation_style": policy_record.remediation_style
            }
            # Cache it
            policy_cache.set(org_id, policy)
            logger.info(f"Policy loaded from database for org_id={org_id}, policy_id={policy_record.id}")
            return policy
        else:
            # No policy exists, use default
            default_policy = {
                "policy_id": None,
                "org_id": org_id,
                **DEFAULT_POLICY
            }
            # Cache default (with shorter TTL would be better, but keeping simple)
            policy_cache.set(org_id, default_policy)
            logger.info(f"Using default policy for org_id={org_id}")
            return default_policy
    except Exception as e:
        logger.error(f"Error loading policy for org_id={org_id}: {e}", exc_info=True)
        # Return default on error
        return {
            "policy_id": None,
            "org_id": org_id,
            **DEFAULT_POLICY
        }
    finally:
        db.close()

def get_policy_id(org_id: str) -> Optional[int]:
    """Get policy_id for org_id (for audit logging)."""
    policy = load_policy(org_id)
    return policy.get("policy_id")

