"""Application entry point for the whatsaid FastAPI server.

Usage:
    # Run directly
    uvicorn whatsaid.api.main:app --reload --port 8000

    # Via the installed console script
    whatsaid-api

    # Override DB path
    WHATSAID_DB_PATH=/path/to/resources.db whatsaid-api
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Whatsaid API",
    description="REST API for visualising WhatsApp chat data extracted by the whatsaid pipeline.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow the Vite dev server (port 5173) and any localhost origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Console script entry point
# ---------------------------------------------------------------------------

def start() -> None:
    """Entry point registered in pyproject.toml as `whatsaid-api`."""
    uvicorn.run(
        "whatsaid.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    start()
