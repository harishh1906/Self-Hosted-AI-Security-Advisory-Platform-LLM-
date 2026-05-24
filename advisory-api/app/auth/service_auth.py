"""
Service-to-Service Authentication (Enterprise Pattern)
Prevents internal abuse and lateral movement attacks.
"""
import hmac
import hashlib
import time
from fastapi import Request, HTTPException, status
from app.config import SERVICE_SECRET_KEY

def verify_service_signature(request: Request, service_name: str, signature: str, body_hash: str = None) -> bool:
    """
    Verify HMAC signature from internal service.
    
    Pattern: HMAC-SHA256(service_name + timestamp + body_hash, secret_key)
    
    Note: FastAPI consumes request body, so services should send X-Body-Hash
    """
    if not SERVICE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Service authentication not configured"
        )
    
    # Get timestamp from header (services should include X-Timestamp)
    timestamp = request.headers.get("X-Timestamp", "")
    
    # HIGH PRIORITY FIX: Require X-Body-Hash header (remove weak fallback)
    if not body_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Body-Hash header required for service authentication"
        )
    
    body_content = body_hash
    
    # Build message: service_name + timestamp + body_hash
    message = f"{service_name}:{timestamp}:{body_content}".encode()
    
    # Compute expected signature
    expected_signature = hmac.new(
        SERVICE_SECRET_KEY.encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison
    return hmac.compare_digest(signature, expected_signature)

def get_service_identity(request: Request) -> dict:
    """
    Extract and validate service identity from headers.
    Returns service info if valid.
    """
    service_name = request.headers.get("X-Service-Name")
    service_signature = request.headers.get("X-Service-Signature")
    
    if not service_name or not service_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Service authentication required: X-Service-Name and X-Service-Signature headers missing"
        )
    
    # Get body hash if provided (services should send SHA256 hash of request body)
    body_hash = request.headers.get("X-Body-Hash", "")
    
    # Verify signature
    if not verify_service_signature(request, service_name, service_signature, body_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service signature"
        )
    
    # Check timestamp (prevent replay attacks - 5 minute window)
    timestamp = request.headers.get("X-Timestamp", "")
    try:
        ts = int(timestamp)
        current_ts = int(time.time())
        if abs(current_ts - ts) > 300:  # 5 minutes
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Request timestamp expired"
            )
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid timestamp"
        )
    
    return {
        "service_name": service_name,
        "auth_type": "service"
    }

