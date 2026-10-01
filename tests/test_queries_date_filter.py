"""Tests for the date-range filter on get_resources().

TDD: these tests define the expected behaviour before the implementation
is added to queries.get_resources().
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from whatsaid.api import queries


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _build_db(tmp_path: Path) -> str:
    """Create a minimal in-memory-style SQLite DB with known data."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Schema (subset needed for these tests)
    cur.executescript(
        """
        CREATE TABLE chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            message_count INTEGER DEFAULT 0,
            first_message_at TEXT,
            last_message_at TEXT,
            import_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL REFERENCES chats(id),
            timestamp TEXT,
            sender TEXT,
            text TEXT,
            imported_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE resources (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id          INTEGER NOT NULL REFERENCES chats(id),
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
            enrichment_error TEXT
        );
        """
    )

    # Insert one chat
    cur.execute("INSERT INTO chats (name) VALUES ('Test Chat')")
    chat_id = cur.lastrowid

    # Insert messages on three different days
    days = ["2024-01-10 10:00:00", "2024-02-15 12:00:00", "2024-03-20 09:00:00"]
    message_ids = []
    for ts in days:
        cur.execute(
            "INSERT INTO messages (chat_id, timestamp, sender, text) VALUES (?, ?, 'Alice', 'check this out')",
            (chat_id, ts),
        )
        message_ids.append(cur.lastrowid)

    # Insert one resource per message
    urls = [
        "https://www.youtube.com/watch?v=aaa",
        "https://www.instagram.com/p/bbb",
        "https://open.spotify.com/track/ccc",
    ]
    for i, (mid, url) in enumerate(zip(message_ids, urls)):
        cur.execute(
            "INSERT INTO resources (chat_id, first_message_id, canonical_url, platform) VALUES (?, ?, ?, ?)",
            (chat_id, mid, url, ["YouTube", "Instagram", "Spotify"][i]),
        )

    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetResourcesDateFilter:
    """Verify that date_from / date_to narrow the result set correctly."""

    def test_no_date_filter_returns_all(self, tmp_path):
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(db_path=db)
        assert total == 3
        assert len(rows) == 3

    def test_date_from_filters_out_earlier_resources(self, tmp_path):
        db = _build_db(tmp_path)
        # Only resources whose message timestamp >= 2024-02-01 should be returned
        total, rows = queries.get_resources(db_path=db, date_from="2024-02-01")
        assert total == 2  # Feb 15 and Mar 20
        canonical_urls = {r["canonical_url"] for r in rows}
        assert "https://www.youtube.com/watch?v=aaa" not in canonical_urls
        assert "https://www.instagram.com/p/bbb" in canonical_urls
        assert "https://open.spotify.com/track/ccc" in canonical_urls

    def test_date_to_filters_out_later_resources(self, tmp_path):
        db = _build_db(tmp_path)
        # Only resources whose message timestamp <= 2024-02-28 should be returned
        total, rows = queries.get_resources(db_path=db, date_to="2024-02-28")
        assert total == 2  # Jan 10 and Feb 15
        canonical_urls = {r["canonical_url"] for r in rows}
        assert "https://open.spotify.com/track/ccc" not in canonical_urls

    def test_date_from_and_date_to_together(self, tmp_path):
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(
            db_path=db, date_from="2024-02-01", date_to="2024-02-28"
        )
        assert total == 1
        assert rows[0]["canonical_url"] == "https://www.instagram.com/p/bbb"

    def test_date_from_exclusive_boundary(self, tmp_path):
        """The boundary date itself (inclusive) should be included."""
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(db_path=db, date_from="2024-01-10")
        assert total == 3  # Jan 10 boundary is inclusive

    def test_date_to_inclusive_boundary(self, tmp_path):
        """Resources on the to-date should be included (end of day)."""
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(db_path=db, date_to="2024-03-20")
        assert total == 3  # Mar 20 boundary is inclusive (entire day)

    def test_date_filter_combined_with_platform_filter(self, tmp_path):
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(
            db_path=db, date_from="2024-01-01", platform="YouTube"
        )
        assert total == 1
        assert rows[0]["platform"] == "YouTube"

    def test_date_out_of_range_returns_empty(self, tmp_path):
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(db_path=db, date_from="2025-01-01")
        assert total == 0
        assert rows == []

    def test_message_timestamp_included_in_result(self, tmp_path):
        """Each returned row should include message_timestamp from the join."""
        db = _build_db(tmp_path)
        total, rows = queries.get_resources(db_path=db)
        assert total == 3
        for row in rows:
            assert "message_timestamp" in row
            assert row["message_timestamp"] is not None
