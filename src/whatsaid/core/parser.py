"""WhatsApp chat export parser.

Reads a ``.txt`` (or previously-extracted) WhatsApp export file, parses
each message (including multi-line continuations), and inserts them into
the ``messages`` table.
"""

from __future__ import annotations

import os
import re

from .db import DEFAULT_DB_PATH, get_cursor

# ---------------------------------------------------------------------------
# Regex: covers standard iOS and Android WhatsApp export formats.
#   - [dd/mm/yy, hh:mm:ss] Sender: text       (iOS with brackets)
#   - dd/mm/yy, hh:mm - Sender: text           (Android with dash)
#   - dd/mm/yy, hh:mm\u202fam/pm - Sender: text  (narrow no-break space before am/pm)
# ---------------------------------------------------------------------------
_MSG_REGEX = re.compile(
    r"^\[?(\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4},\s+\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f][AaPp][Mm])?)\]?\s+-\s+([^:]+): (.*)$"
)


def _parse_lines(lines: list[str]) -> list[dict[str, str | list[str]]]:
    """Parse raw chat lines into a list of message dicts."""
    messages: list[dict] = []
    current_msg: dict | None = None

    for line in lines:
        line = line.strip("\n")
        if not line:
            continue

        match = _MSG_REGEX.match(line)
        if match:
            if current_msg:
                messages.append(current_msg)
            timestamp, sender, text = match.groups()
            current_msg = {"timestamp": timestamp, "sender": sender, "text": [text]}
        else:
            # Continuation of previous message
            if current_msg:
                current_msg["text"].append(line)

    if current_msg:
        messages.append(current_msg)

    return messages


def parse_whatsapp_chat(
    filepath: str,
    chat_id: int,
    db_path: str = DEFAULT_DB_PATH,
) -> tuple[int, int]:
    """Parse *filepath* and insert messages for *chat_id* into the database.

    Uses ``INSERT OR IGNORE`` with the composite ``UNIQUE`` constraint to
    safely skip already-seen messages when appending to an existing chat.

    Returns:
        (inserted, total) — messages actually written vs. total parsed.
    Raises:
        FileNotFoundError: if *filepath* does not exist.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Chat file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as fh:
        raw_lines = fh.readlines()

    messages = _parse_lines(raw_lines)
    total = len(messages)
    inserted = 0

    with get_cursor(db_path) as cursor:
        for msg in messages:
            full_text = "\n".join(msg["text"]).strip()  # type: ignore[arg-type]
            if not full_text:
                continue
            cursor.execute(
                """
                INSERT OR IGNORE INTO messages (chat_id, timestamp, sender, text)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, msg["timestamp"], msg["sender"], full_text),
            )
            inserted += cursor.rowcount

    return inserted, total
