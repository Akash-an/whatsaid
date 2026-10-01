"""FastAPI router definitions for the whatsaid API.

Routes:
    GET  /api/stats
    GET  /api/chats
    GET  /api/resources         (paginated, filterable)
    GET  /api/resources/{id}
    PATCH /api/resources/{id}
    POST /api/resources/{id}/enrich
    GET  /api/messages          (paginated, searchable)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response

from ..core.db import DEFAULT_DB_PATH

# Walk up from this file (src/whatsaid/api/routes.py) to the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FALLBACK_DB_PATH = str(_PROJECT_ROOT / "data" / "resources.db")
from . import queries
from .schemas import (
    ChatResponse,
    EnrichmentResponse,
    MessageResponse,
    NLQueryRequest,
    NLQueryResponse,
    PaginatedResponse,
    ResourceResponse,
    ResourceStatusUpdate,
    StatsResponse,
)

router = APIRouter(prefix="/api")

from pydantic import BaseModel
from ..logging import get_logger

logger = get_logger(__name__)
ui_logger = get_logger("whatsaid_ui")

# Resolve DB path; prefer env var, then look for resources.db in the data/ directory.
def _db() -> str:
    return os.environ.get("WHATSAID_DB_PATH", _FALLBACK_DB_PATH)


class UILogRequest(BaseModel):
    level: str
    namespace: str
    msg: str
    data: Optional[dict] = None
    path: Optional[str] = None


@router.post("/ui-log", status_code=204, summary="Accept client-side logs")
def accept_ui_log(body: UILogRequest, request: Request):
    if body.level not in ("warn", "error"):
        raise HTTPException(status_code=400, detail="Only warn/error levels accepted")
    
    # Very basic rate limiting info could go here, omitting for simplicity unless requested
    log_func = ui_logger.warning if body.level == "warn" else ui_logger.error
    
    extra = {
        "namespace": body.namespace,
        "data": body.data,
        "path": body.path,
    }
    if request:
        extra["ua"] = request.headers.get("user-agent")
        if not extra["path"]:
            extra["path"] = request.headers.get("referer")
            
    log_func(body.msg, extra=extra)
    return Response(status_code=204)


@router.get("/logs", summary="Fetch application logs")
def get_logs(
    file: str = Query("whatsaid.log", description="Log file to read (whatsaid.log, ui.log, llm.log)"),
    limit: int = Query(1000, le=5000),
):
    """Read the latest NDJSON log entries from a specific log file."""
    import json
    
    allowed_files = {"whatsaid.log", "ui.log", "llm.log"}
    if file not in allowed_files:
        raise HTTPException(status_code=400, detail="Invalid log file")

    log_dir_str = os.environ.get("WHATSAID_LOG_DIR", "logs")
    if os.path.isabs(log_dir_str):
        log_path = Path(log_dir_str) / file
    else:
        log_path = _PROJECT_ROOT / log_dir_str / file

    if not log_path.exists():
        return []

    logs = []
    try:
        # For simplicity with <10MB files, read all and reverse
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
                
            if len(logs) >= limit:
                break
    except Exception as e:
        logger.error("Failed to read logs", extra={"exc": str(e), "file": file})
        raise HTTPException(status_code=500, detail="Failed to read log file")

    return logs


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


from .schemas import ChatInsightsResponse

@router.get(
    "/chats/{chat_id}/insights",
    response_model=ChatInsightsResponse,
    summary="Detailed summary and insights for a specific chat",
)
def get_chat_insights(
    chat_id: int,
    date_from: Optional[str] = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
) -> ChatInsightsResponse:
    data = queries.get_chat_insights(
        chat_id=chat_id,
        db_path=_db(),
        date_from=date_from,
        date_to=date_to,
    )
    if data is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatInsightsResponse(**data)

from .schemas import ChatSummaryResponse

@router.post(
    "/chats/{chat_id}/summary",
    response_model=ChatSummaryResponse,
    summary="Generate an LLM summary for a specific chat and date range",
)
def generate_chat_summary(
    chat_id: int,
    date_from: Optional[str] = Query(None, description="Inclusive start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Inclusive end date (YYYY-MM-DD)"),
) -> ChatSummaryResponse:
    from ..llm.summarizer import run_summary_workflow
    
    result = run_summary_workflow(
        chat_id=chat_id,
        date_from=date_from,
        date_to=date_to,
        db_path=_db()
    )
    
    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result.get("error", "Summary generation failed"))
        
    summary_text = result.get("final_summary") or "No summary generated."
    
    if summary_text != "No messages found for this date range.":
        from .queries import save_chat_summary
        save_chat_summary(_db(), chat_id, date_from, date_to, summary_text)
        
    return ChatSummaryResponse(
        summary=summary_text,
        error=None
    )

from .schemas import SavedSummary

@router.get(
    "/chats/{chat_id}/summaries",
    response_model=list[SavedSummary],
    summary="Get past summaries for a chat",
)
def list_chat_summaries(chat_id: int) -> list[SavedSummary]:
    from .queries import get_chat_summaries
    rows = get_chat_summaries(_db(), chat_id)
    return [SavedSummary(**row) for row in rows]


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@router.get("/resources", response_model=PaginatedResponse, summary="Paginated resource list")
def list_resources(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=5000)] = 50,
    chat_id: Optional[int] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="Inclusive start date (YYYY-MM-DD) based on the message timestamp"),
    date_to: Optional[str] = Query(None, description="Inclusive end date (YYYY-MM-DD) based on the message timestamp"),
) -> PaginatedResponse:
    total, rows = queries.get_resources(
        db_path=_db(),
        page=page,
        page_size=page_size,
        chat_id=chat_id,
        platform=platform,
        status=status,
        search=search,
        date_from=date_from,
        date_to=date_to,
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


@router.get(
    "/resources/{resource_id}",
    response_model=ResourceResponse,
    summary="Get a single resource by ID",
)
def get_resource(resource_id: int) -> ResourceResponse:
    """Fetch a single resource row — useful for polling enrichment status."""
    row = queries.get_resource_by_id(resource_id, db_path=_db())
    if row is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")
    return ResourceResponse(**row)


@router.post(
    "/resources/{resource_id}/enrich",
    response_model=EnrichmentResponse,
    summary="Trigger LLM enrichment workflow for a resource",
)
def enrich_resource(
    resource_id: int,
    background_tasks: BackgroundTasks,
) -> EnrichmentResponse:
    """Kick off the LangGraph enrichment workflow as a background task.

    The workflow:
      1. Fetches live metadata from the URL (platform-aware: YouTube oEmbed,
         Instagram oEmbed, or generic HTML scrape).
      2. Sends the metadata + chat context to the LLM to synthesise a clean
         title, 1-sentence summary, and 3-5 tags.
      3. Persists the results back to the resources table.

    The endpoint returns immediately with ``status='pending'``.
    Poll ``GET /api/resources/{id}`` to check ``enrichment_status``.

    Error codes:
        404 — Resource not found.
    """
    row = queries.get_resource_by_id(resource_id, db_path=_db())
    if row is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")

    # Mark as pending synchronously so the UI can update immediately
    queries.set_enrichment_status(resource_id, "pending", db_path=_db())

    # Import lazily to avoid slow startup when the enricher is not needed
    from ..llm.resource_enricher import run_enrichment_workflow

    db_path_snapshot = _db()
    background_tasks.add_task(run_enrichment_workflow, dict(row), db_path_snapshot)

    return EnrichmentResponse(
        resource_id=resource_id,
        status="pending",
        message="Enrichment started. Poll GET /api/resources/{id} for status.",
    )


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


# ---------------------------------------------------------------------------
# Natural-language query (Ask page)
# ---------------------------------------------------------------------------

_PAGE_SIZE = 200


@router.post(
    "/query",
    response_model=NLQueryResponse,
    summary="Translate a natural-language question into SQL and execute it",
)
def nl_query(body: NLQueryRequest) -> NLQueryResponse:
    """Accept a free-form English question, generate a safe SQL SELECT via the
    LLM, execute it against the database, and return paginated results.

    Error codes:
        400 — empty question, LLM returned unsafe/invalid SQL, or SQL
              execution failed (e.g. LLM hallucinated a non-existent column).
        503 — LLM API call failed (network error, missing API key, etc.).
    """
    from ..llm.text_to_sql import (
        InvalidSQLError,
        generate_sql,
        validate_and_clean_sql,
    )

    question = (body.question or "").strip()
    if not question:
        logger.warning("Empty question rejected")
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    logger.info("NL question received", extra={"question": question[:200]})

    # -- Step 1: Generate SQL via LLM ------------------------------------
    try:
        raw_sql = generate_sql(question)
    except RuntimeError as exc:
        logger.error("LLM call failed (503)", extra={"exc": str(exc)})
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # -- Step 2: Validate and sanitise the generated SQL -----------------
    try:
        clean_sql = validate_and_clean_sql(raw_sql)
    except InvalidSQLError as exc:
        logger.warning("SQL unsafe/invalid (400)", extra={"raw_sql": raw_sql, "reason": str(exc)})
        raise HTTPException(
            status_code=400,
            detail=f"The generated query was unsafe or invalid: {exc}",
        ) from exc

    # -- Step 3: Execute with pagination ---------------------------------
    try:
        columns, rows, total_count = queries.execute_raw_select(
            clean_sql,
            db_path=_db(),
            page=body.page,
            page_size=_PAGE_SIZE,
        )
    except ValueError as exc:
        logger.error("SQL execution error (400)", extra={"sql": clean_sql, "exc": str(exc)})
        raise HTTPException(
            status_code=400,
            detail=f"Query execution failed: {exc}",
        ) from exc

    import math
    total_pages = math.ceil(total_count / _PAGE_SIZE) if total_count else 1

    return NLQueryResponse(
        sql=clean_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        total_count=total_count,
        page=body.page,
        total_pages=total_pages,
    )
