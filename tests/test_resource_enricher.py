"""Tests for llm/resource_enricher.py — LangGraph enrichment workflow.

All external calls (fetchers + LLM) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from whatsaid.llm.fetchers import FetchResult
from whatsaid.llm.resource_enricher import (
    EnrichmentState,
    run_enrichment_workflow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resource(platform: str = "YouTube", url: str = "https://youtube.com/watch?v=abc") -> dict:
    return {
        "id": 42,
        "canonical_url": url,
        "platform": platform,
        "context": "Someone shared this in the group",
        "title": None,
        "notes": None,
        "tags": None,
    }


# ---------------------------------------------------------------------------
# run_enrichment_workflow
# ---------------------------------------------------------------------------

def test_workflow_youtube_success():
    """Full workflow should save title, tags, and notes for a YouTube resource."""
    resource = _make_resource("YouTube", "https://www.youtube.com/watch?v=abc")
    fetch_result = FetchResult(
        title="Cool Tutorial",
        author="TeachingChannel",
        description=None,
        thumbnail_url="https://i.ytimg.com/vi/abc/default.jpg",
    )
    llm_output = {
        "title": "Cool Tutorial by TeachingChannel",
        "tags": "tutorial,coding,python",
        "notes": "A beginner-friendly Python tutorial.",
    }

    with (
        patch("whatsaid.llm.resource_enricher.fetch_for_url", return_value=fetch_result),
        patch("whatsaid.llm.resource_enricher._call_llm", return_value=llm_output),
        patch("whatsaid.llm.resource_enricher._save_enrichment") as mock_save,
    ):
        state = run_enrichment_workflow(resource, db_path=":memory:")

    assert state["status"] == "done"
    mock_save.assert_called_once()
    save_kwargs = mock_save.call_args.kwargs
    assert save_kwargs["title"] == "Cool Tutorial by TeachingChannel"
    assert "python" in save_kwargs["tags"]


def test_workflow_fetch_failure_marks_failed():
    """When the fetcher returns an error, the workflow should mark status=failed."""
    resource = _make_resource("YouTube", "https://www.youtube.com/watch?v=bad")
    fetch_result = FetchResult(error="HTTP 404")

    with (
        patch("whatsaid.llm.resource_enricher.fetch_for_url", return_value=fetch_result),
        patch("whatsaid.llm.resource_enricher._save_enrichment") as mock_save,
    ):
        state = run_enrichment_workflow(resource, db_path=":memory:")

    assert state["status"] == "failed"
    assert "error" in state
    mock_save.assert_called_once()
    assert mock_save.call_args.kwargs["status"] == "failed"


def test_workflow_llm_exception_marks_failed():
    """LLM call failure should result in failed status, not an unhandled exception."""
    resource = _make_resource("Other", "https://myblog.com/post")
    fetch_result = FetchResult(title="Blog Post", description="Nice article")

    with (
        patch("whatsaid.llm.resource_enricher.fetch_for_url", return_value=fetch_result),
        patch("whatsaid.llm.resource_enricher._call_llm", side_effect=RuntimeError("LLM down")),
        patch("whatsaid.llm.resource_enricher._save_enrichment") as mock_save,
    ):
        state = run_enrichment_workflow(resource, db_path=":memory:")

    assert state["status"] == "failed"
    mock_save.assert_called_once()


def test_workflow_instagram_uses_og_data():
    """Instagram resources should be fetched and enriched with og: metadata."""
    resource = _make_resource("Instagram", "https://www.instagram.com/p/XYZ/")
    fetch_result = FetchResult(
        title="@foodie: Delicious pasta 🍝",
        description="123 likes, 7 comments",
        thumbnail_url="https://example.com/img.jpg",
    )
    llm_output = {
        "title": "Pasta Recipe by @foodie",
        "tags": "food,pasta,instagram",
        "notes": "A pasta recipe shared on Instagram.",
    }

    with (
        patch("whatsaid.llm.resource_enricher.fetch_for_url", return_value=fetch_result),
        patch("whatsaid.llm.resource_enricher._call_llm", return_value=llm_output),
        patch("whatsaid.llm.resource_enricher._save_enrichment") as mock_save,
    ):
        state = run_enrichment_workflow(resource, db_path=":memory:")

    assert state["status"] == "done"
    save_kwargs = mock_save.call_args.kwargs
    assert "pasta" in save_kwargs["tags"] or "food" in save_kwargs["tags"]
