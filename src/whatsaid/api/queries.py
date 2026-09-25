"""Database query helpers for the API layer.

These functions are deliberately kept separate from ``core/db.py`` to avoid
coupling the pipeline layer to the API layer.  They are thin, read-optimised
query wrappers that return plain ``dict`` objects (converted from
``sqlite3.Row``) so they compose cleanly with Pydantic models.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from ..core.db import DEFAULT_DB_PATH, get_connection


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats(db_path: str = DEFAULT_DB_PATH) -> dict:
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM messages")
    total_messages: int = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM resources")
    total_resources: int = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM chats")
    total_chats: int = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM resources WHERE status = 'To Review'")
    pending_review: int = cur.fetchone()[0]

    # Platform breakdown — group nulls/empties as "Unknown"
    cur.execute("""
        SELECT COALESCE(NULLIF(platform, ''), 'Unknown') AS platform, COUNT(*) AS count
        FROM resources
        GROUP BY platform
        ORDER BY count DESC
        LIMIT 20
    """)
    platform_breakdown = _rows_to_dicts(cur.fetchall())

    # Daily message counts (last 90 days), excluding rows where timestamp is unparseable
    cur.execute("""
        SELECT DATE(timestamp) AS date, COUNT(*) AS count
        FROM messages
        WHERE timestamp IS NOT NULL
          AND DATE(timestamp) IS NOT NULL
        GROUP BY DATE(timestamp)
        ORDER BY date ASC
        LIMIT 90
    """)
    daily_message_counts = _rows_to_dicts(cur.fetchall())

    # Top link senders
    cur.execute("""
        SELECT m.sender, COUNT(r.id) AS count
        FROM resources r
        JOIN messages m ON r.first_message_id = m.id
        WHERE m.sender IS NOT NULL
        GROUP BY m.sender
        ORDER BY count DESC
        LIMIT 10
    """)
    top_link_senders = _rows_to_dicts(cur.fetchall())

    conn.close()

    return {
        "total_messages": total_messages,
        "total_resources": total_resources,
        "total_chats": total_chats,
        "pending_review": pending_review,
        "platform_breakdown": platform_breakdown,
        "daily_message_counts": daily_message_counts,
        "top_link_senders": top_link_senders,
    }


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

def get_chats(db_path: str = DEFAULT_DB_PATH) -> list[dict]:
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM chats ORDER BY updated_at DESC")
    rows = _rows_to_dicts(cur.fetchall())
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

def get_resources(
    *,
    db_path: str = DEFAULT_DB_PATH,
    page: int = 1,
    page_size: int = 50,
    chat_id: Optional[int] = None,
    platform: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[int, list[dict]]:
    """Return (total_count, page_of_rows) with optional filters."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    conditions: list[str] = []
    params: list = []

    if chat_id is not None:
        conditions.append("r.chat_id = ?")
        params.append(chat_id)
    if platform:
        conditions.append("r.platform = ?")
        params.append(platform)
    if status:
        conditions.append("r.status = ?")
        params.append(status)
    if search:
        conditions.append("(r.canonical_url LIKE ? OR r.context LIKE ? OR r.notes LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    base_query = f"""
        FROM resources r
        LEFT JOIN chats c ON r.chat_id = c.id
        LEFT JOIN messages m ON r.first_message_id = m.id
        {where_clause}
    """

    cur.execute(f"SELECT COUNT(*) {base_query}", params)
    total: int = cur.fetchone()[0]

    offset = (page - 1) * page_size
    cur.execute(
        f"""
        SELECT r.*, c.name AS chat_name, m.sender
        {base_query}
        ORDER BY r.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, offset],
    )
    rows = _rows_to_dicts(cur.fetchall())
    conn.close()
    return total, rows


def update_resource(
    resource_id: int,
    *,
    db_path: str = DEFAULT_DB_PATH,
    status: Optional[str] = None,
    notes: Optional[str] = None,
    title: Optional[str] = None,
    tags: Optional[str] = None,
) -> Optional[dict]:
    """Apply partial updates to a resource. Returns the updated row or None if not found."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT id FROM resources WHERE id = ?", (resource_id,))
    if not cur.fetchone():
        conn.close()
        return None

    updates: list[str] = []
    params: list = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if tags is not None:
        updates.append("tags = ?")
        params.append(tags)

    if updates:
        params.append(resource_id)
        cur.execute(
            f"UPDATE resources SET {', '.join(updates)} WHERE id = ?", params
        )
        conn.commit()

    cur.execute(
        "SELECT r.*, c.name AS chat_name FROM resources r LEFT JOIN chats c ON r.chat_id = c.id WHERE r.id = ?",
        (resource_id,),
    )
    row = _row_to_dict(cur.fetchone())
    conn.close()
    return row


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def get_messages(
    *,
    db_path: str = DEFAULT_DB_PATH,
    page: int = 1,
    page_size: int = 100,
    chat_id: Optional[int] = None,
    search: Optional[str] = None,
) -> tuple[int, list[dict]]:
    """Return (total_count, page_of_rows)."""
    conn = get_connection(db_path)
    cur = conn.cursor()

    conditions: list[str] = []
    params: list = []

    if chat_id is not None:
        conditions.append("chat_id = ?")
        params.append(chat_id)
    if search:
        conditions.append("(text LIKE ? OR sender LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    cur.execute(f"SELECT COUNT(*) FROM messages {where_clause}", params)
    total: int = cur.fetchone()[0]

    offset = (page - 1) * page_size
    cur.execute(
        f"SELECT * FROM messages {where_clause} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    )
    rows = _rows_to_dicts(cur.fetchall())
    conn.close()
    return total, rows
