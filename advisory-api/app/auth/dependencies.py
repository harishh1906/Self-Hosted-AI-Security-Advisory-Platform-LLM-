from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.auth.jwt import decode_access_token
from app.auth.service_auth import get_service_identity

security = HTTPBearer(auto_error=False)

def get_current_user_or_service(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Dual authentication: Supports both user JWT and service HMAC.
    Returns identity info (user or service).
    """
    # Try service authentication first (for internal service calls)
    # CRITICAL FIX: If X-Service-Name is present, service auth MUST succeed or fail hard
    # No fallback to user auth to prevent authentication bypass
    service_name = request.headers.get("X-Service-Name")
    if service_name:
        # Service auth is MANDATORY if header present - no fallback
        service_identity = get_service_identity(request)  # Raises HTTPException on failure
        return {
            **service_identity,
            "org_id": request.headers.get("X-Org-ID")  # Service passes org_id
        }
    
    # Try user JWT authentication
    if credentials:
        try:
            token = credentials.credentials
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            role = payload.get("role", "viewer")
            org_id = payload.get("org_id")  # Extract org_id from token
            
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )
            
            return {
                "user_id": user_id,
                "role": role,
                "org_id": org_id,
                "auth_type": "user"
            }
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed"
            )
    
    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: JWT token or service signature"
    )

# Backward compatibility
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Legacy function for user-only authentication."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    try:
        token = credentials.credentials
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        role = payload.get("role", "viewer")
        org_id = payload.get("org_id")
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
        
        return {
            "user_id": user_id,
            "role": role,
            "org_id": org_id,
            "auth_type": "user"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )

