import logging
from fastapi import APIRouter, Depends
from app.auth.dependencies import get_current_user_or_service
from app.health import get_readiness_status
from app.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health Diagnostics"])

@router.get("/health")
def health_check():
    """Public health check endpoint."""
    return {"status": "ok"}

@router.get("/internal/health")
def internal_health_check(identity: dict = Depends(get_current_user_or_service)):
    """
    Internal health and readiness endpoint.
    Returns detailed status of all dependencies and circuit breaker state.
    """
    health_status = get_readiness_status()
    circuit_state = circuit_breaker.get_state()
    
    return {
        **health_status,
        "circuit_breaker": circuit_state
    }
