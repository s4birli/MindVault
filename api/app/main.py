"""Main FastAPI application."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .routers import items, auth, ingest

# Create FastAPI app
app = FastAPI(
    title="MindVault API",
    description="Minimal MindVault API with JWT authentication",
    version="1.0.0",
)

# Add CORS middleware (permissive for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["authentication"])
app.include_router(items.router, prefix="/items", tags=["items"])
app.include_router(ingest.router, prefix="/ingest", tags=["ingestion"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
    )
