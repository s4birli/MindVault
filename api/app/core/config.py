"""Configuration settings for the MindVault API."""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    
    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://mindvault:mindvault@mindvault_db:5432/mindvault"
    
    # JWT Settings
    JWT_ALG: str = "HS256"
    JWT_SECRET: str  # Required - no default for security
    JWT_ISS: Optional[str] = None
    JWT_AUD: Optional[str] = None
    JWT_LEEWAY_SEC: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
