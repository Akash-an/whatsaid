"""Message enrichment: URL extraction, deduplication, and context windowing.

``get_context_window`` is kept separate from ``process_messages`` so that
context-fetching logic can be tested or reused independently.
"""

from __future__ import annotations

import sqlite3

from ..core.db import DEFAULT_DB_PATH, get_connection, get_cursor
from .url_utils import extract_urls, get_platform, normalize_url


# ---------------------------------------------------------------------------
# Context windowing
# ---------------------------------------------------------------------------

def get_context_window(
    message_id: int,
    *,
    window_size: int = 3,
    db_path: str = DEFAULT_DB_PATH,
) -> str:
    """Return a formatted string of the messages surrounding *message_id*.

    The target message is wrapped with ``>>>`` / ``<<<`` markers.
    *window_size* controls how many messages before and after are included.
    """
    conn: sqlite3.Connection = get_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT sender, text FROM messages WHERE id < ? ORDER BY id DESC LIMIT ?",
        (message_id, window_size),
    )
    prev_msgs = cursor.fetchall()[::-1]  # reverse to chronological order

    cursor.execute("SELECT sender, text FROM messages WHERE id = ?", (message_id,))
    current_msg = cursor.fetchone()

    cursor.execute(
        "SELECT sender, text FROM messages WHERE id > ? ORDER BY id ASC LIMIT ?",
        (message_id, window_size),
    )
    next_msgs = cursor.fetchall()
    conn.close()

    lines: list[str] = []
    for msg in prev_msgs:
        lines.append(f"{msg['sender']}: {msg['text']}")
    lines.append(f">>> {current_msg['sender']}: {current_msg['text']} <<<")
    for msg in next_msgs:
        lines.append(f"{msg['sender']}: {msg['text']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# URL extraction & resource insertion
# ---------------------------------------------------------------------------

def process_messages(*, chat_id: int, db_path: str = DEFAULT_DB_PATH) -> int:
    """Find URLs in every message for *chat_id*, deduplicate, and insert into ``resources``.

    Deduplication is scoped per chat via ``UNIQUE(chat_id, canonical_url)``,
    so the same URL can appear in multiple chats as separate resources.

    Returns the number of new resources inserted.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, text FROM messages WHERE chat_id = ?", (chat_id,))
    all_messages = cursor.fetchall()
    conn.close()

    inserted = 0
    with get_cursor(db_path) as write_cursor:
        for msg in all_messages:
            msg_id: int = msg["id"]
            text: str = msg["text"]

            for url in extract_urls(text):
                canonical = normalize_url(url)
                platform = get_platform(canonical)

                # Pre-check before the more expensive context fetch.
                write_cursor.execute(
                    "SELECT id FROM resources WHERE chat_id = ? AND canonical_url = ?",
                    (chat_id, canonical),
                )
                if write_cursor.fetchone():
                    continue  # already exists for this chat — deduplicated

                context = get_context_window(msg_id, db_path=db_path)
                write_cursor.execute(
                    """
                    INSERT OR IGNORE INTO resources
                        (chat_id, first_message_id, original_url, canonical_url, platform, context, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'To Review')
                    """,
                    (chat_id, msg_id, url, canonical, platform, context),
                )
                inserted += write_cursor.rowcount

    print(f"Extracted and deduplicated {inserted} unique resources.")
    return inserted
