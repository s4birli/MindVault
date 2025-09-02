"""Authentication router for JWT token generation."""

from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import jwt

from ..core.config import settings

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


# Hardcoded credentials for now (in production, use database with hashed passwords)
VALID_CREDENTIALS = {
    "sabirli31@gmail.com": "1453Mhmt1++ZAM@"
}


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(login_data: LoginRequest):
    """
    Authenticate user and return JWT token.
    
    Request Body:
        username: User email address
        password: User password
        
    Returns:
        access_token: JWT token for API access
        token_type: Always "bearer"
        expires_in: Token expiration time in seconds
    """
    # Validate credentials
    if (login_data.username not in VALID_CREDENTIALS or 
        VALID_CREDENTIALS[login_data.username] != login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create JWT token
    expires_in = 3600  # 1 hour in seconds
    payload = {
        "iss": settings.JWT_ISS,
        "aud": settings.JWT_AUD,
        "sub": login_data.username,
        "exp": datetime.utcnow() + timedelta(seconds=expires_in),
        "iat": datetime.utcnow(),
        "email": login_data.username,
        "user_id": 1  # For now, hardcode user_id as 1
    }
    
    access_token = jwt.encode(
        payload, 
        settings.JWT_SECRET, 
        algorithm=settings.JWT_ALG
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in
    )


@router.post("/login", response_model=TokenResponse)
async def login(login_data: LoginRequest):
    """
    Alias for /token endpoint for easier access.
    """
    return await login_for_access_token(login_data)
