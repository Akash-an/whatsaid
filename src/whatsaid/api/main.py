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
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

# Load .env so that OPENAI_API_KEY (and any other secrets) are available
# to the LLM client regardless of how the server is started.
load_dotenv()

from .routes import router
from ..logging import configure_logging, get_logger
from .middleware import request_logging_middleware

# Configure logging at startup
configure_logging()
logger = get_logger(__name__)

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
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.debug("CORS origins registered", extra={"origins": origins})

app.middleware("http")(request_logging_middleware)

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
    port = 8000
    log_level = os.environ.get("WHATSAID_LOG_LEVEL", "INFO")
    logger.info("Server starting", extra={"port": port, "log_level": log_level})
    uvicorn.run(
        "whatsaid.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )


if __name__ == "__main__":
    start()
