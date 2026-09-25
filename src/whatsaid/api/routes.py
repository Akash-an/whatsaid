"""FastAPI router definitions for the whatsaid API.

Routes:
    GET  /api/stats
    GET  /api/chats
    GET  /api/resources         (paginated, filterable)
    PATCH /api/resources/{id}
    GET  /api/messages          (paginated, searchable)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query

from ..core.db import DEFAULT_DB_PATH

# Walk up from this file (src/whatsaid/api/routes.py) to the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FALLBACK_DB_PATH = str(_PROJECT_ROOT / "data" / "resources.db")
from . import queries
from .schemas import (
    ChatResponse,
    MessageResponse,
    PaginatedResponse,
    ResourceResponse,
    ResourceStatusUpdate,
    StatsResponse,
)

router = APIRouter(prefix="/api")

# Resolve DB path; prefer env var, then look for resources.db at project root.
def _db() -> str:
    return os.environ.get("WHATSAID_DB_PATH", _FALLBACK_DB_PATH)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=StatsResponse, summary="Aggregated dashboard stats")
def get_stats() -> StatsResponse:
    data = queries.get_stats(db_path=_db())
    return StatsResponse(**data)


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

@router.get("/chats", response_model=list[ChatResponse], summary="All imported chats")
def list_chats() -> list[ChatResponse]:
    rows = queries.get_chats(db_path=_db())
    return [ChatResponse(**r) for r in rows]


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@router.get("/resources", response_model=PaginatedResponse, summary="Paginated resource list")
def list_resources(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    chat_id: Optional[int] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> PaginatedResponse:
    total, rows = queries.get_resources(
        db_path=_db(),
        page=page,
        page_size=page_size,
        chat_id=chat_id,
        platform=platform,
        status=status,
        search=search,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ResourceResponse(**r) for r in rows],
    )


@router.patch(
    "/resources/{resource_id}",
    response_model=ResourceResponse,
    summary="Update resource status / metadata",
)
def patch_resource(resource_id: int, body: ResourceStatusUpdate) -> ResourceResponse:
    updated = queries.update_resource(
        resource_id,
        db_path=_db(),
        status=body.status,
        notes=body.notes,
        title=body.title,
        tags=body.tags,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")
    return ResourceResponse(**updated)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

@router.get("/messages", response_model=PaginatedResponse, summary="Paginated message list")
def list_messages(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 100,
    chat_id: Optional[int] = None,
    search: Optional[str] = None,
) -> PaginatedResponse:
    total, rows = queries.get_messages(
        db_path=_db(),
        page=page,
        page_size=page_size,
        chat_id=chat_id,
        search=search,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[MessageResponse(**r) for r in rows],
    )
