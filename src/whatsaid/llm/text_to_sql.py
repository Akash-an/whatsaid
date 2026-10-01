"""Natural-language to SQL translation for the whatsaid query feature.

Public API
----------
    generate_sql(question)          → raw SQL string from the LLM (unvalidated)
    validate_and_clean_sql(raw)     → cleaned, safe SQL string or raises InvalidSQLError
    InvalidSQLError                 → raised when the SQL fails safety checks
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from litellm import completion

# Load .env at project root so OPENAI_API_KEY is available before any call.
load_dotenv()

# ---------------------------------------------------------------------------
# Schema context injected into every LLM prompt
# ---------------------------------------------------------------------------

SCHEMA_CONTEXT = """
-- SQLite schema for 'resources.db' (WhatsApp chat analytics)

CREATE TABLE chats (
    id               INTEGER PRIMARY KEY,
    name             TEXT,           -- human-assigned chat name
    message_count    INTEGER,
    first_message_at TEXT,           -- format: 'YYYY-MM-DD HH:MM:SS'
    last_message_at  TEXT,           -- format: 'YYYY-MM-DD HH:MM:SS'
    import_count     INTEGER,
    created_at       TEXT,
    updated_at       TEXT
);

CREATE TABLE messages (
    id          INTEGER PRIMARY KEY,
    chat_id     INTEGER,             -- FK -> chats.id
    timestamp   TEXT,               -- format: 'YYYY-MM-DD HH:MM:SS'  ← ONLY messages has timestamp
    sender      TEXT,               -- person who sent the message
    text        TEXT,               -- raw message content
    imported_at TEXT
);

CREATE TABLE resources (
    id               INTEGER PRIMARY KEY,
    chat_id          INTEGER,        -- FK -> chats.id
    first_message_id INTEGER,        -- FK -> messages.id (the message that first shared this URL)
    original_url     TEXT,
    canonical_url    TEXT,           -- deduplicated, tracking-param-stripped URL
    platform         TEXT,           -- e.g. 'Instagram', 'YouTube', 'Google Maps'
    tags             TEXT,
    title            TEXT,
    context          TEXT,           -- surrounding message context (3 messages before/after)
    notes            TEXT,
    status           TEXT            -- values: 'To Review', 'Approved', 'Archived'
    -- ⚠️  resources does NOT have a timestamp or sender column.
    --     To filter resources by date or sender, JOIN with messages:
    --     JOIN messages m ON resources.first_message_id = m.id
    --     then use m.timestamp and m.sender.
);
""".strip()

# ---------------------------------------------------------------------------
# Example queries — shown to the LLM to anchor correct JOIN patterns
# ---------------------------------------------------------------------------

_EXAMPLE_QUERIES = """
-- Q: links shared in the last two months
SELECT r.canonical_url, r.platform, m.sender, m.timestamp
FROM resources r
JOIN messages m ON r.first_message_id = m.id
WHERE m.timestamp >= date('now', '-2 months')

-- Q: who shared the most links?
SELECT m.sender, COUNT(r.id) AS link_count
FROM resources r
JOIN messages m ON r.first_message_id = m.id
GROUP BY m.sender
ORDER BY link_count DESC

-- Q: all YouTube links pending review
SELECT r.canonical_url, r.status, m.sender, m.timestamp
FROM resources r
JOIN messages m ON r.first_message_id = m.id
WHERE r.platform = 'YouTube' AND r.status = 'To Review'

-- Q: how many messages were sent in June 2024?
SELECT COUNT(*) AS message_count
FROM messages
WHERE timestamp >= '2024-06-01' AND timestamp < '2024-07-01'

-- Q: links shared by Alice
SELECT r.canonical_url, r.platform, r.status
FROM resources r
JOIN messages m ON r.first_message_id = m.id
WHERE m.sender = 'Alice'

-- Q: how many total messages per chat?
SELECT c.name, c.message_count
FROM chats c
ORDER BY c.message_count DESC
""".strip()

SYSTEM_PROMPT = f"""
You are a SQLite query generator for a WhatsApp chat analytics database.

Given a natural-language question, output ONLY a single valid SQLite SELECT statement.

Rules:
- Output raw SQL only. No explanations, no markdown code fences, no inline comments.
- The query must be read-only. Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, ATTACH, PRAGMA, or DETACH.
- Do NOT add a LIMIT or OFFSET clause; the caller handles pagination.
- Use the exact table and column names from the schema below.
- CRITICAL: The 'resources' table has NO timestamp or sender column. To filter
  resources by date or by who shared the link, you MUST JOIN with messages:
      JOIN messages m ON resources.first_message_id = m.id
  then use m.timestamp and m.sender.
- If a question is ambiguous, write the most reasonable query.

Database schema:
{SCHEMA_CONTEXT}

Example queries (follow these JOIN patterns):
{_EXAMPLE_QUERIES}
""".strip()

# ---------------------------------------------------------------------------
# Safety constants
# ---------------------------------------------------------------------------

# Keywords that must never appear anywhere in the SQL (case-insensitive).
_FORBIDDEN_KEYWORDS: frozenset[str] = frozenset({
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE",
    "ALTER", "ATTACH", "DETACH", "PRAGMA",
})

# A regex that matches a forbidden keyword as a whole word (not a substring).
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _FORBIDDEN_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Matches markdown code fences: ```sql ... ``` or ``` ... ```
_FENCE_RE = re.compile(r"^```[a-z]*\n?|```$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class InvalidSQLError(ValueError):
    """Raised when LLM output fails the safety or syntax validation checks."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_and_clean_sql(raw: str) -> str:
    """Strip markdown fences and validate that *raw* is a safe SELECT statement.

    Args:
        raw: The raw string returned by the LLM (may include code fences).

    Returns:
        The cleaned SQL string (no fences, stripped whitespace).

    Raises:
        InvalidSQLError: If the SQL is empty, not a SELECT, contains forbidden
            keywords, or contains SQL comment syntax (``--``).
    """
    # 1. Strip markdown fences.
    cleaned = _FENCE_RE.sub("", raw).strip()

    # 2. Strip trailing semicolons — LLMs often terminate SQL with one, but
    #    SQLite raises "near ';': syntax error" when we later append LIMIT/OFFSET.
    cleaned = cleaned.rstrip(";").rstrip()

    # 3. Reject empty input.
    if not cleaned:
        raise InvalidSQLError("SQL is empty — the LLM returned no query.")

    # 4. Reject SQL comments (potential injection vector).
    if "--" in cleaned:
        raise InvalidSQLError(
            "SQL contains comment syntax ('--') which is not allowed."
        )

    # 4. Reject any forbidden DML/DDL keywords (whole-word match, case-insensitive).
    match = _FORBIDDEN_RE.search(cleaned)
    if match:
        raise InvalidSQLError(
            f"SQL contains forbidden keyword '{match.group()}'. "
            "Only read-only SELECT statements are permitted."
        )

    # 5. Assert the statement opens with SELECT.
    first_token = cleaned.split()[0].upper()
    if first_token != "SELECT":
        raise InvalidSQLError(
            f"SQL must begin with SELECT, but got '{first_token}'. "
            "Only read-only SELECT statements are permitted."
        )

    return cleaned


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def generate_sql(question: str) -> str:
    """Call the LLM to translate a natural-language question into SQL.

    The model is resolved from the ``WHATSAID_SQL_MODEL`` environment variable,
    defaulting to ``gpt-4o-mini``.

    Args:
        question: A free-form English question about the WhatsApp chat data.

    Returns:
        The raw text response from the LLM (not yet validated).

    Raises:
        RuntimeError: If the LLM call fails (network error, missing API key, etc.).
    """
    import time
    from ..logging import get_logger
    logger = get_logger(__name__)
    
    model = os.environ.get("WHATSAID_SQL_MODEL", "gpt-4o-mini")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    logger.debug("LLM call start", extra={"model": model, "question": question[:200]})
    logger.debug("Full prompt sent", extra={"system_prompt": SYSTEM_PROMPT, "user_message": question, "llm": True})

    start_time = time.time()
    try:
        response = completion(model=model, messages=messages, temperature=0)
        duration_ms = int((time.time() - start_time) * 1000)
        content = response.choices[0].message.content or ""
        
        logger.info("LLM call success", extra={
            "model": model,
            "duration_ms": duration_ms,
            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
            "completion_tokens": getattr(response.usage, "completion_tokens", 0),
            "llm": True
        })
        logger.debug("Full raw response", extra={"raw_sql": content, "llm": True})
        
        return content
    except Exception as exc:
        logger.error("LLM call failed", extra={"exc": str(exc)})
        raise RuntimeError(f"LLM call failed: {exc}") from exc
