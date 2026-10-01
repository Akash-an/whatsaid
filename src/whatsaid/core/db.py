"""Database connection, schema management, and chat CRUD operations."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

DEFAULT_DB_PATH = "data/resources.db"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return an open SQLite connection with row-factory and foreign keys enabled."""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_cursor(db_path: str = DEFAULT_DB_PATH) -> Generator[sqlite3.Cursor, None, None]:
    """Context manager that yields a cursor and commits on clean exit."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        yield cursor
        conn.commit()
    finally:
        conn.close()


from ..logging import get_logger
logger = get_logger(__name__)

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create the full schema if it does not already exist."""
    logger.debug("DB opened", extra={"db_path": db_path})
    with get_cursor(db_path) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT UNIQUE NOT NULL,
                message_count    INTEGER DEFAULT 0,
                first_message_at TEXT,
                last_message_at  TEXT,
                import_count     INTEGER DEFAULT 0,
                created_at       TEXT DEFAULT (datetime('now')),
                updated_at       TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                timestamp   TEXT,
                sender      TEXT,
                text        TEXT,
                imported_at TEXT DEFAULT (datetime('now')),
                UNIQUE (chat_id, timestamp, sender, text)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)"
        )
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id          INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                first_message_id INTEGER REFERENCES messages(id),
                original_url     TEXT,
                canonical_url    TEXT,
                platform         TEXT,
                tags             TEXT,
                title            TEXT,
                context          TEXT,
                notes            TEXT,
                status           TEXT DEFAULT 'To Review',
                enrichment_status TEXT,
                enriched_at      TEXT,
                enrichment_error TEXT,
                UNIQUE (chat_id, canonical_url)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_resources_chat ON resources(chat_id)"
        )
        # Migration: add enrichment columns to pre-existing databases that
        # were created before this schema version.
        for col, col_type in [
            ("enrichment_status", "TEXT"),
            ("enriched_at", "TEXT"),
            ("enrichment_error", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE resources ADD COLUMN {col} {col_type}")
            except Exception:
                pass  # Column already exists — safe to ignore
                
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_summaries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                date_from   TEXT,
                date_to     TEXT,
                summary     TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_summaries_chat ON chat_summaries(chat_id)"
        )
        logger.info("Schema migrated", extra={"db_path": db_path})

def clear_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Delete the database file and re-initialise a clean schema."""
    if os.path.exists(db_path):
        os.remove(db_path)
    init_db(db_path)


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------

def get_chat_by_name(name: str, db_path: str = DEFAULT_DB_PATH) -> sqlite3.Row | None:
    """Return the chat row with the given name, or None if not found."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chats WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_chat_by_id(chat_id: int, db_path: str = DEFAULT_DB_PATH) -> sqlite3.Row | None:
    """Return the chat row with the given id, or None if not found."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chats WHERE id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_all_chats(db_path: str = DEFAULT_DB_PATH) -> list[sqlite3.Row]:
    """Return all chat rows ordered by most-recently updated."""
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chats ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows


def create_chat(name: str, db_path: str = DEFAULT_DB_PATH) -> int:
    """Insert a new chat row and return its id."""
    with get_cursor(db_path) as cursor:
        cursor.execute("INSERT INTO chats (name) VALUES (?)", (name,))
        return cursor.lastrowid  # type: ignore[return-value]


def update_chat_stats(chat_id: int, db_path: str = DEFAULT_DB_PATH) -> None:
    """Recompute and persist message_count, timestamps, and import_count."""
    with get_cursor(db_path) as cursor:
        cursor.execute("""
            UPDATE chats SET
                message_count    = (SELECT COUNT(*)       FROM messages WHERE chat_id = ?),
                first_message_at = (SELECT MIN(timestamp) FROM messages WHERE chat_id = ?),
                last_message_at  = (SELECT MAX(timestamp) FROM messages WHERE chat_id = ?),
                import_count     = import_count + 1,
                updated_at       = datetime('now')
            WHERE id = ?
        """, (chat_id, chat_id, chat_id, chat_id))


def rename_chat(old_name: str, new_name: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Rename a chat. Returns True if found and renamed, False if not found."""
    with get_cursor(db_path) as cursor:
        cursor.execute(
            "UPDATE chats SET name = ?, updated_at = datetime('now') WHERE name = ?",
            (new_name, old_name),
        )
        return cursor.rowcount > 0


def delete_chat(name: str, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Delete a chat and all its messages/resources via CASCADE.

    Returns True if the chat was found and deleted, False otherwise.
    """
    with get_cursor(db_path) as cursor:
        cursor.execute("DELETE FROM chats WHERE name = ?", (name,))
        return cursor.rowcount > 0
