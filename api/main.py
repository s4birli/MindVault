from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MindVault API (dev)")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    import os
    return {
        "ok": True,
        "env": {
            "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
            "S3_ENDPOINT": os.getenv("S3_ENDPOINT"),
            "S3_BUCKET": os.getenv("S3_BUCKET"),
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        }
    }


# Routers
from .routers import search, ask, index, ingest, agent, threads  # noqa: E402
app.include_router(search.router)
app.include_router(ask.router)
app.include_router(index.router)
app.include_router(ingest.router)
app.include_router(agent.router)
app.include_router(threads.router)


@app.get("/")
def root():
    return JSONResponse({"ok": True, "endpoints": ["/health", "/search", "/ask", "/index", "/ingest", "/agent", "/threads"]})
