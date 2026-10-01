"""Pydantic schemas (response models) for the whatsaid API.

All models use ``model_config = ConfigDict(from_attributes=True)`` so that they
can be constructed directly from ``sqlite3.Row`` objects via ``model_validate``.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    message_count: int
    first_message_at: Optional[str]
    last_message_at: Optional[str]
    import_count: int
    created_at: str
    updated_at: str


class ParticipantCount(BaseModel):
    sender: str
    count: int

class ChatSummaryResponse(BaseModel):
    summary: str
    error: Optional[str] = None

class SavedSummary(BaseModel):
    id: int
    chat_id: int
    date_from: Optional[str]
    date_to: Optional[str]
    summary: str
    created_at: str


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    timestamp: Optional[str]
    sender: Optional[str]
    text: Optional[str]
    imported_at: str


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

class ResourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    first_message_id: Optional[int]
    original_url: Optional[str]
    canonical_url: Optional[str]
    platform: Optional[str]
    tags: Optional[str]
    title: Optional[str]
    context: Optional[str]
    notes: Optional[str]
    status: Optional[str]
    enrichment_status: Optional[str] = None
    enriched_at: Optional[str] = None
    enrichment_error: Optional[str] = None

    # Joined field from chats table (may be None if query doesn't join)
    chat_name: Optional[str] = None
    # Joined fields from messages table
    sender: Optional[str] = None
    message_timestamp: Optional[str] = None


class ResourceStatusUpdate(BaseModel):
    """Payload for PATCH /api/resources/{id}."""
    status: Optional[str] = None
    notes: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[str] = None


class EnrichmentResponse(BaseModel):
    """Response body for POST /api/resources/{id}/enrich."""
    resource_id: int
    status: str   # 'pending' | 'done' | 'failed'
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Stats (Dashboard)
# ---------------------------------------------------------------------------

class PlatformCount(BaseModel):
    platform: str
    count: int


class DailyMessageCount(BaseModel):
    date: str
    count: int


class SenderLinkCount(BaseModel):
    sender: str
    count: int


class StatsResponse(BaseModel):
    total_messages: int
    total_resources: int
    total_chats: int
    pending_review: int
    platform_breakdown: list[PlatformCount]
    daily_message_counts: list[DailyMessageCount]
    top_link_senders: list[SenderLinkCount]


class ChatInsightsResponse(BaseModel):
    chat_id: int
    chat_name: str
    total_messages: int
    participants: list[ParticipantCount]
    daily_activity: list[DailyMessageCount]
    top_platforms: list[PlatformCount]


# ---------------------------------------------------------------------------
# Pagination wrapper
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list


# ---------------------------------------------------------------------------
# Natural-language query (Ask page)
# ---------------------------------------------------------------------------

class NLQueryRequest(BaseModel):
    """Request body for POST /api/query."""

    question: str
    page: int = 1


class NLQueryResponse(BaseModel):
    """Response body for POST /api/query."""

    sql: str            # Generated SELECT shown to the user for transparency
    columns: list[str]  # Column header names derived from the query result
    rows: list[list]    # Page of result rows, each serialised as a plain list
    row_count: int      # Number of rows on this page
    total_count: int    # Total matching rows across all pages
    page: int           # Current page (1-based)
    total_pages: int    # Total number of pages

