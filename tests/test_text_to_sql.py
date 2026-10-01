"""Tests for the NL → SQL text_to_sql module.

Written before implementation (TDD). All tests should initially fail and
pass once the corresponding production code is in place.

Tests cover:
    - validate_and_clean_sql() — safety guardrails
    - execute_raw_select()     — pagination + correctness
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
import pytest

from whatsaid.llm.text_to_sql import validate_and_clean_sql, InvalidSQLError
from whatsaid.api.queries import execute_raw_select


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_temp_db() -> str:
    """Create a temp SQLite DB with a tiny messages table and return its path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            sender TEXT,
            text TEXT
        )
    """)
    for i in range(1, 11):
        conn.execute(
            "INSERT INTO messages (sender, text) VALUES (?, ?)",
            (f"sender_{i}", f"hello {i}"),
        )
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# validate_and_clean_sql
# ---------------------------------------------------------------------------

class TestValidateAndCleanSql:
    def test_raises_on_empty_string(self):
        with pytest.raises(InvalidSQLError, match="empty"):
            validate_and_clean_sql("")

    def test_raises_on_whitespace_only(self):
        with pytest.raises(InvalidSQLError, match="empty"):
            validate_and_clean_sql("   \n  ")

    def test_raises_on_drop_statement(self):
        with pytest.raises(InvalidSQLError, match="SELECT"):
            validate_and_clean_sql("DROP TABLE messages")

    def test_raises_on_delete_statement(self):
        with pytest.raises(InvalidSQLError, match="SELECT"):
            validate_and_clean_sql("DELETE FROM messages")

    def test_raises_on_update_statement(self):
        with pytest.raises(InvalidSQLError, match="SELECT"):
            validate_and_clean_sql("UPDATE messages SET text='x'")

    def test_raises_on_insert_statement(self):
        with pytest.raises(InvalidSQLError, match="SELECT"):
            validate_and_clean_sql("INSERT INTO messages VALUES (1, 'a', 'b')")

    def test_raises_on_comment_injection(self):
        """A leading comment before SELECT must be rejected."""
        with pytest.raises(InvalidSQLError):
            validate_and_clean_sql("-- drop everything\nSELECT 1")

    def test_raises_on_forbidden_keyword_in_body(self):
        """Forbidden keyword inside a SELECT body is also rejected."""
        with pytest.raises(InvalidSQLError):
            validate_and_clean_sql("SELECT * FROM messages; DROP TABLE messages")

    def test_raises_on_pragma(self):
        with pytest.raises(InvalidSQLError):
            validate_and_clean_sql("PRAGMA table_info(messages)")

    def test_raises_on_mixed_case_forbidden(self):
        with pytest.raises(InvalidSQLError):
            validate_and_clean_sql("DeLeTe FROM messages")

    def test_accepts_valid_select(self):
        sql = validate_and_clean_sql("SELECT * FROM messages")
        assert sql.strip().upper().startswith("SELECT")

    def test_accepts_valid_select_lowercase(self):
        sql = validate_and_clean_sql("select id from messages where id = 1")
        assert sql.strip().lower().startswith("select")

    def test_strips_markdown_fences(self):
        raw = "```sql\nSELECT * FROM messages\n```"
        sql = validate_and_clean_sql(raw)
        assert "```" not in sql
        assert sql.strip().upper().startswith("SELECT")

    def test_strips_fences_without_language_hint(self):
        raw = "```\nSELECT 1\n```"
        sql = validate_and_clean_sql(raw)
        assert "```" not in sql

    def test_strips_surrounding_whitespace(self):
        sql = validate_and_clean_sql("  \n  SELECT 1  \n  ")
        assert not sql.startswith(" ")
        assert not sql.endswith(" ")

    def test_accepts_multiline_select(self):
        raw = """
        SELECT m.sender, COUNT(*) AS cnt
        FROM messages m
        GROUP BY m.sender
        ORDER BY cnt DESC
        """
        sql = validate_and_clean_sql(raw)
        assert sql.strip().upper().startswith("SELECT")

    def test_strips_trailing_semicolon(self):
        """LLMs frequently terminate SQL with ';' which breaks LIMIT appending."""
        sql = validate_and_clean_sql("SELECT * FROM messages;")
        assert not sql.endswith(";")

    def test_strips_trailing_semicolon_with_whitespace(self):
        sql = validate_and_clean_sql("SELECT * FROM messages ;  ")
        assert not sql.rstrip().endswith(";")


# ---------------------------------------------------------------------------
# execute_raw_select
# ---------------------------------------------------------------------------

class TestExecuteRawSelect:
    def test_returns_all_columns(self):
        db = _make_temp_db()
        cols, rows, total = execute_raw_select(
            "SELECT id, sender, text FROM messages",
            db_path=db,
        )
        assert cols == ["id", "sender", "text"]
        os.unlink(db)

    def test_returns_correct_row_count(self):
        db = _make_temp_db()
        _, rows, total = execute_raw_select(
            "SELECT * FROM messages",
            db_path=db,
            page=1,
            page_size=200,
        )
        assert total == 10
        assert len(rows) == 10
        os.unlink(db)

    def test_pagination_page_1(self):
        db = _make_temp_db()
        _, rows, total = execute_raw_select(
            "SELECT * FROM messages ORDER BY id",
            db_path=db,
            page=1,
            page_size=3,
        )
        assert total == 10
        assert len(rows) == 3
        assert rows[0][0] == 1  # first row id = 1
        os.unlink(db)

    def test_pagination_page_2(self):
        db = _make_temp_db()
        _, rows, total = execute_raw_select(
            "SELECT * FROM messages ORDER BY id",
            db_path=db,
            page=2,
            page_size=3,
        )
        assert total == 10
        assert len(rows) == 3
        assert rows[0][0] == 4  # page 2 starts at row 4
        os.unlink(db)

    def test_last_page_returns_remainder(self):
        db = _make_temp_db()
        _, rows, total = execute_raw_select(
            "SELECT * FROM messages ORDER BY id",
            db_path=db,
            page=4,
            page_size=3,
        )
        assert total == 10
        assert len(rows) == 1  # 10 rows, 3 per page → page 4 has 1 row
        os.unlink(db)

    def test_total_count_reflects_full_result_set(self):
        db = _make_temp_db()
        _, rows, total = execute_raw_select(
            "SELECT * FROM messages WHERE id <= 5",
            db_path=db,
            page=1,
            page_size=2,
        )
        assert total == 5   # full result set is 5 rows
        assert len(rows) == 2  # only 2 returned on this page
        os.unlink(db)

    def test_rows_are_lists(self):
        db = _make_temp_db()
        _, rows, _ = execute_raw_select(
            "SELECT id FROM messages LIMIT 1",
            db_path=db,
        )
        assert isinstance(rows[0], list)
        os.unlink(db)

    def test_invalid_sql_raises_value_error(self):
        db = _make_temp_db()
        with pytest.raises(ValueError, match="SQL execution error"):
            execute_raw_select("SELECT * FROM nonexistent_table", db_path=db)
        os.unlink(db)

    def test_tolerates_trailing_semicolon(self):
        """execute_raw_select must not crash when SQL has a trailing semicolon
        (defence-in-depth, in case a semicolon bypasses validate_and_clean_sql)."""
        db = _make_temp_db()
        _, rows, total = execute_raw_select(
            "SELECT * FROM messages;",
            db_path=db,
        )
        assert total == 10
        os.unlink(db)
