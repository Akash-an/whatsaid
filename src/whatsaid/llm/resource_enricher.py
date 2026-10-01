"""LangGraph-based resource enrichment workflow.

The workflow takes a resource dict (from the database) and runs three nodes:

  1. ``fetch_metadata``  — calls the appropriate platform fetcher to get raw
                           page metadata (title, description, thumbnail, etc.)
  2. ``synthesize``      — sends the metadata + conversational context to the
                           LLM to produce a clean title, a 1-sentence summary,
                           and 3-5 relevant tags.
  3. ``save``            — persists the enriched fields back to the ``resources``
                           table and marks ``enrichment_status = 'done'``.

Errors at any node are caught, the status is set to ``'failed'``, and the
workflow still terminates cleanly (no uncaught exceptions escape).

Public API
----------
    run_enrichment_workflow(resource: dict, db_path: str) -> EnrichmentState
"""

from __future__ import annotations

import json
import re
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from ..core.db import get_cursor
from ..llm.client import LLMClient
from ..llm.fetchers import FetchResult, fetch_for_url


# ---------------------------------------------------------------------------
# Workflow state
# ---------------------------------------------------------------------------

class EnrichmentState(TypedDict):
    """Shared mutable state threaded through every LangGraph node."""

    # Input fields (set before the graph runs)
    resource_id: int
    canonical_url: str
    platform: str
    context: Optional[str]           # Conversational context from surrounding messages
    db_path: str

    # Intermediate fields (set by fetch_metadata node)
    fetch_result: Optional[FetchResult]

    # Output fields (set by synthesize node)
    enriched_title: Optional[str]
    enriched_tags: Optional[str]     # Comma-separated tag string
    enriched_notes: Optional[str]    # 1-sentence summary

    # Terminal fields
    status: str                      # 'pending' | 'done' | 'failed'
    error: Optional[str]


from ..logging import get_logger
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Node: fetch_metadata
# ---------------------------------------------------------------------------

def _node_fetch_metadata(state: EnrichmentState) -> EnrichmentState:
    """Dispatch to the correct platform fetcher and attach result to state."""
    logger.debug("fetch_metadata node enter", extra={"url": state["canonical_url"]})
    try:
        result: FetchResult = fetch_for_url(state["canonical_url"])
        if result.error:
            logger.warning("Fetch failed", extra={"error": result.error})
            return {
                **state,
                "fetch_result": result,
                "status": "failed",
                "error": f"Fetch failed: {result.error}",
            }
        logger.debug("Fetch result received", extra={"title": result.title, "author": result.author, "has_content": result.has_content()})
        return {**state, "fetch_result": result}
    except Exception as exc:
        logger.warning("Fetch failed", extra={"error": str(exc)})
        return {
            **state,
            "fetch_result": None,
            "status": "failed",
            "error": f"Unexpected fetch error: {exc}",
        }


# ---------------------------------------------------------------------------
# Node: synthesize
# ---------------------------------------------------------------------------

_SYNTHESIS_PROMPT = """\
You are an assistant that enriches link metadata for a group chat resource library.

Given the following information about a URL, produce a clean JSON object with these exact keys:
- "title": A short, clear title for the resource (max 100 chars). If already good, reuse it.
- "tags": 3 to 5 comma-separated lowercase tags that best categorise this content.
- "notes": A single sentence (max 150 chars) summarising what this resource is about.

URL: {url}
Platform: {platform}
Raw title: {title}
Raw description: {description}
Author/Channel: {author}
Conversational context (the chat messages around when this was shared):
{context}

Respond ONLY with a valid JSON object and no other text.
"""

_INSTAGRAM_SYNTHESIS_PROMPT = """\
You are an assistant that enriches Instagram link metadata for a group chat resource library.

If a full caption is provided, use it directly to summarize the post and extract tags.
If the caption is missing, you must infer what the post is about based on the account handle
and conversational context. Do NOT default to generic tags like "social-media", "instagram",
or "entertainment" — those are useless.

Produce a JSON object with these exact keys:
- "title": A short descriptive title (max 80 chars).
- "tags": 3 to 5 comma-separated lowercase tags describing the CONTENT TOPIC.
  Base these on the caption (if available) or the account handle.
- "notes": One sentence (max 150 chars) on what this is likely about.

URL: {url}
Instagram account handle: {account_handle}
oEmbed / Fetch title: {title}
Post Caption: {description}
Conversational context:
{context}

Respond ONLY with a valid JSON object and no other text.
"""


def _node_synthesize(state: EnrichmentState) -> EnrichmentState:
    """Call the LLM to synthesize enriched metadata from the fetched raw data."""
    if state.get("status") == "failed":
        return state  # Skip if already failed

    logger.debug("synthesize node enter", extra={"resource_id": state["resource_id"]})
    fetch_result: Optional[FetchResult] = state.get("fetch_result")
    try:
        llm_output = _call_llm(
            url=state["canonical_url"],
            platform=state.get("platform", "Unknown"),
            title=fetch_result.title if fetch_result else None,
            description=fetch_result.description if fetch_result else None,
            author=fetch_result.author if fetch_result else None,
            context=state.get("context"),
            fetch_extra=fetch_result.extra if fetch_result else None,
        )
        return {
            **state,
            "enriched_title": llm_output.get("title"),
            "enriched_tags": llm_output.get("tags"),
            "enriched_notes": llm_output.get("notes"),
        }
    except Exception as exc:
        return {
            **state,
            "status": "failed",
            "error": f"LLM synthesis failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Node: save
# ---------------------------------------------------------------------------

def _node_save(state: EnrichmentState) -> EnrichmentState:
    """Persist enriched fields and final status to the database."""
    final_status = state.get("status") if state.get("status") == "failed" else "done"
    logger.debug("save node: DB write", extra={"resource_id": state["resource_id"], "final_status": final_status})
    error_msg = state.get("error") if final_status == "failed" else None
    try:
        _save_enrichment(
            resource_id=state["resource_id"],
            db_path=state["db_path"],
            title=state.get("enriched_title"),
            tags=state.get("enriched_tags"),
            notes=state.get("enriched_notes"),
            status=final_status,
            error=error_msg,
        )
    except Exception as exc:
        # Best-effort — log but don't re-raise so the API response is still clean
        logger.error("Save failed", extra={"exc": str(exc)})
        final_status = "failed"
        state = {**state, "error": f"Save failed: {exc}"}

    return {**state, "status": final_status}


# ---------------------------------------------------------------------------
# Router (conditional edge)
# ---------------------------------------------------------------------------

def _should_synthesize(state: EnrichmentState) -> str:
    """Route to 'synthesize' if fetch succeeded, or skip straight to 'save'."""
    route = "save" if state.get("status") == "failed" else "synthesize"
    logger.debug("_should_synthesize routing", extra={"route": route})
    return route


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def _build_graph() -> object:
    graph = StateGraph(EnrichmentState)

    graph.add_node("fetch_metadata", _node_fetch_metadata)
    graph.add_node("synthesize", _node_synthesize)
    graph.add_node("save", _node_save)

    graph.add_edge(START, "fetch_metadata")
    graph.add_conditional_edges("fetch_metadata", _should_synthesize, ["synthesize", "save"])
    graph.add_edge("synthesize", "save")
    graph.add_edge("save", END)

    return graph.compile()


_COMPILED_GRAPH = None  # Lazy singleton


def _get_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = _build_graph()
    return _COMPILED_GRAPH


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_enrichment_workflow(resource: dict, db_path: str) -> EnrichmentState:
    """Run the enrichment workflow for a single resource.

    Args:
        resource: A dict with at least ``id``, ``canonical_url``, ``platform``,
                  ``context`` keys (as returned by ``queries.get_resources``).
        db_path:  Path to the SQLite database file.

    Returns:
        The final ``EnrichmentState`` with ``status`` set to ``'done'`` or
        ``'failed'``.
    """
    import time
    start_time = time.time()
    initial_state: EnrichmentState = {
        "resource_id": resource["id"],
        "canonical_url": resource.get("canonical_url") or resource.get("original_url", ""),
        "platform": resource.get("platform") or "Unknown",
        "context": resource.get("context"),
        "db_path": db_path,
        "fetch_result": None,
        "enriched_title": None,
        "enriched_tags": None,
        "enriched_notes": None,
        "status": "pending",
        "error": None,
    }
    
    logger.info("Enrichment workflow started", extra={"resource_id": resource["id"], "url": initial_state["canonical_url"]})
    graph = _get_graph()
    result = graph.invoke(initial_state)
    
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info("Enrichment workflow done", extra={"resource_id": resource["id"], "status": result["status"], "duration_ms": duration_ms})
    return result


# ---------------------------------------------------------------------------
# Internal helpers (separate for easy mocking in tests)
# ---------------------------------------------------------------------------

def _call_llm(
    *,
    url: str,
    platform: str,
    title: Optional[str],
    description: Optional[str],
    author: Optional[str],
    context: Optional[str],
    fetch_extra: Optional[dict] = None,
) -> dict:
    """Send enrichment prompt to the LLM and parse the JSON response.

    Routes Instagram URLs to a dedicated prompt that uses the account handle
    as its primary signal, avoiding generic "social-media" tags.

    Returns a dict with keys: title, tags, notes.
    Raises RuntimeError if the LLM response cannot be parsed.
    """
    url_lower = url.lower()
    is_instagram = "instagram.com" in url_lower

    if is_instagram:
        account_handle = (fetch_extra or {}).get("account_handle") or author or "(unknown)"
        prompt = _INSTAGRAM_SYNTHESIS_PROMPT.format(
            url=url,
            account_handle=account_handle,
            title=title or "(title not available)",
            description=description or "(caption not available)",
            context=context or "(no conversational context available)",
        )
    else:
        prompt = _SYNTHESIS_PROMPT.format(
            url=url,
            platform=platform,
            title=title or "(not available)",
            description=description or "(not available)",
            author=author or "(not available)",
            context=context or "(no context available)",
        )

    client = LLMClient()
    logger.debug("Full synthesis prompt", extra={"prompt": prompt, "url": url, "platform": platform, "llm": True})
    
    import time
    start = time.time()
    raw = client.generate(prompt=prompt)
    duration_ms = int((time.time() - start) * 1000)
    
    logger.debug("LLM synthesis response", extra={"raw_response": raw, "duration_ms": duration_ms, "llm": True})

    # Extract JSON block (LLMs sometimes wrap it in ```json ... ```)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        logger.error("JSON parse error", extra={"raw": raw[:200]})
        raise RuntimeError(f"LLM returned non-JSON response: {raw[:200]}")

    try:
        parsed = json.loads(json_match.group(0))
        logger.info("Synthesis success", extra={"duration_ms": duration_ms, "llm": True})
        return parsed
    except json.JSONDecodeError as exc:
        logger.error("JSON parse error", extra={"raw": raw[:200], "exc": str(exc)})
        raise RuntimeError(f"LLM JSON parse error: {exc} — raw: {raw[:200]}") from exc


def _save_enrichment(
    resource_id: int,
    *,
    db_path: str,
    title: Optional[str],
    tags: Optional[str],
    notes: Optional[str],
    status: str,
    error: Optional[str] = None,
) -> None:
    """Write enriched fields, status, and any error message back to the resources table."""
    with get_cursor(db_path) as cursor:
        cursor.execute(
            """
            UPDATE resources
            SET title              = COALESCE(?, title),
                tags               = COALESCE(?, tags),
                notes              = COALESCE(?, notes),
                enrichment_status  = ?,
                enrichment_error   = ?,
                enriched_at        = datetime('now')
            WHERE id = ?
            """,
            (title, tags, notes, status, error, resource_id),
        )
