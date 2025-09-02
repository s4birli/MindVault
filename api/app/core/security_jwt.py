"""JWT Bearer token validation."""

from typing import Dict, Any
import jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import settings

# HTTP Bearer security scheme
bearer_scheme = HTTPBearer()


async def require_jwt(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> Dict[str, Any]:
    """
    Dependency that validates JWT Bearer token.
    
    Returns:
        Dict containing the decoded JWT claims
        
    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        # Decode and validate the token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALG],
            issuer=settings.JWT_ISS if settings.JWT_ISS else None,
            audience=settings.JWT_AUD if settings.JWT_AUD else None,
            leeway=settings.JWT_LEEWAY_SEC,
        )
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_id(payload: Dict[str, Any] = Depends(require_jwt)) -> int:
    """
    Extract user ID from JWT payload.
    
    Args:
        payload: Decoded JWT payload
        
    Returns:
        User ID as integer
        
    Raises:
        HTTPException: 401 if user ID is missing from token
    """
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return int(user_id)
