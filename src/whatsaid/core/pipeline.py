"""End-to-end pipeline orchestration with interactive chat identity.

Entry points:
    run()          — import or append a chat export
    list_chats()   — print a table of all known chats
    rename_chat()  — rename a chat by its current name
    delete_chat()  — delete a chat and all its data (with confirmation)
    export()       — regenerate the Excel file without re-importing
"""

from __future__ import annotations

import difflib
import os
import shutil
import sys
import tempfile
import zipfile

from .db import (
    DEFAULT_DB_PATH,
    create_chat,
    delete_chat as _db_delete_chat,
    get_all_chats,
    get_chat_by_name,
    get_chat_by_id,
    init_db,
    rename_chat as _db_rename_chat,
    update_chat_stats,
)
from .parser import parse_whatsapp_chat
from ..utils.enrichment import process_messages
from ..io.export import generate_excel

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _prompt(message: str) -> str:
    """Read a non-empty line from stdin. Exits cleanly on Ctrl-C / EOF."""
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)


def _confirm(prompt: str = "Proceed? [y/N]: ", *, yes: bool = False) -> bool:
    if yes:
        return True
    return _prompt(prompt).lower() in ("y", "yes")


def _fuzzy_suggest(name: str, existing_names: list[str]) -> list[str]:
    return difflib.get_close_matches(name, existing_names, n=3, cutoff=0.6)


def _extract_chat_from_zip(zip_path: str, extract_to: str) -> str:
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_to)
        txt_files = [f for f in z.namelist() if f.endswith(".txt")]
        if not txt_files:
            raise ValueError("No .txt file found in the zip archive.")
        chat_filename = txt_files[0]
        return os.path.join(extract_to, chat_filename)


# ---------------------------------------------------------------------------
# Chat confirmation screens
# ---------------------------------------------------------------------------

def _show_existing(chat: object) -> None:
    print()
    print("  ✦ EXISTING CHAT FOUND")
    print(f"  {'Name':<14}: {chat['name']}")
    print(f"  {'Messages':<14}: {chat['message_count']:,}")
    print(f"  {'Last imported':<14}: {chat['last_message_at'] or 'unknown'}")
    print(f"  {'Action':<14}: Append new messages only.")
    print()


def _show_new(name: str) -> None:
    print()
    print("  ✦ NEW CHAT")
    print(f"  {'Name':<14}: {name}")
    print(f"  {'Action':<14}: Create a new chat and import all messages.")
    print()


# ---------------------------------------------------------------------------
# Chat identity resolution
# ---------------------------------------------------------------------------

def _resolve_chat(
    chat_name: str | None,
    db_path: str,
    *,
    yes: bool,
) -> tuple[int, bool]:
    """Interactively resolve a chat name to ``(chat_id, is_new)``.

    If *chat_name* is None the user is prompted. If there is no exact match,
    fuzzy suggestions are shown. The user must confirm before any DB write
    happens.
    """
    if not chat_name:
        chat_name = _prompt("Chat name: ")
        if not chat_name:
            print("Error: chat name cannot be empty.", file=sys.stderr)
            sys.exit(1)

    # --- Exact match ---
    existing = get_chat_by_name(chat_name, db_path)
    if existing:
        _show_existing(existing)
        if not _confirm(yes=yes):
            print("Aborted.")
            sys.exit(0)
        return existing["id"], False

    # --- Fuzzy suggestions ---
    all_names = [c["name"] for c in get_all_chats(db_path)]
    suggestions = _fuzzy_suggest(chat_name, all_names)

    if suggestions:
        print(f'\n  ⚠  No exact match for "{chat_name}"')
        print("  Did you mean one of these?\n")
        for i, s in enumerate(suggestions, 1):
            chat = get_chat_by_name(s, db_path)
            last = chat["last_message_at"] or "never"
            print(f'    {i}. {s}  ({chat["message_count"]:,} messages, last imported {last})')
        new_idx = len(suggestions) + 1
        print(f'    {new_idx}. Create new chat named "{chat_name}"')
        print()

        raw = _prompt(f"Choice [1-{new_idx}]: ")
        try:
            idx = int(raw) - 1
        except ValueError:
            idx = new_idx - 1  # default to creating new

        if 0 <= idx < len(suggestions):
            chosen = get_chat_by_name(suggestions[idx], db_path)
            _show_existing(chosen)
            if not _confirm(yes=yes):
                print("Aborted.")
                sys.exit(0)
            return chosen["id"], False

    # --- New chat ---
    _show_new(chat_name)
    if not _confirm(yes=yes):
        print("Aborted.")
        sys.exit(0)
    chat_id = create_chat(chat_name, db_path)
    return chat_id, True


# ---------------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------------

def run(
    filepath: str,
    output: str = "Extracted_Resources.xlsx",
    db_path: str = DEFAULT_DB_PATH,
    chat_name: str | None = None,
    yes: bool = False,
) -> None:
    """Import or append a WhatsApp chat export.

    Args:
        filepath:  Path to a ``.txt`` or ``.zip`` WhatsApp export.
        output:    Destination Excel file name.
        db_path:   SQLite database path.
        chat_name: Pre-supplied chat name (skips the name prompt).
        yes:       Skip the confirmation prompt (for scripted use).
    """
    from ..logging import get_logger
    logger = get_logger(__name__)
    
    logger.info("Run started", extra={"filepath": filepath, "chat_name": chat_name})
    init_db(db_path)

    chat_id, is_new = _resolve_chat(chat_name, db_path, yes=yes)
    logger.info("Chat resolved", extra={"chat_id": chat_id, "is_new": is_new})
    
    chat = get_chat_by_id(chat_id, db_path)
    if not chat:
        raise RuntimeError("Chat not found after resolution.")
    resolved_name = chat["name"]

    resources_dir = os.path.abspath(os.path.join("resources", resolved_name))
    os.makedirs(resources_dir, exist_ok=True)

    dest_filepath = os.path.join(resources_dir, os.path.basename(filepath))
    if os.path.abspath(filepath) != os.path.abspath(dest_filepath):
        shutil.copy2(filepath, dest_filepath)

    target_file = dest_filepath
    if dest_filepath.lower().endswith(".zip"):
        try:
            target_file = _extract_chat_from_zip(dest_filepath, resources_dir)
        except Exception as exc:
            raise RuntimeError(f"Failed to extract zip: {exc}") from exc

    final_output = os.path.join(resources_dir, os.path.basename(output))

    basename = os.path.basename(target_file)
    print(f"--- Parsing {basename} ---")
    inserted, total = parse_whatsapp_chat(target_file, chat_id=chat_id, db_path=db_path)
    skipped = total - inserted
    if skipped:
        print(f"    {inserted:,} new · {skipped:,} already seen (skipped)")
    else:
        print(f"    {inserted:,} messages inserted")

    update_chat_stats(chat_id, db_path)

    print("--- Extracting resources & context ---")
    new_resources = process_messages(chat_id=chat_id, db_path=db_path)

    print(f"--- Exporting to {final_output} ---")
    generate_excel(final_output, db_path=db_path)
    logger.info("Export done", extra={"output_path": final_output, "new_resources": new_resources})

    verb = "Imported" if is_new else "Appended"
    print(f"\n✅ Done! {verb} {inserted:,} messages · {new_resources} new resources found.")


def list_chats(db_path: str = DEFAULT_DB_PATH) -> None:
    """Print a formatted table of all known chats."""
    init_db(db_path)
    chats = get_all_chats(db_path)
    if not chats:
        print("No chats found. Run `whatsaid run <file>` to import one.")
        return

    print(f"\n  {'ID':<4}  {'Name':<30}  {'Messages':>8}  {'Last Imported'}")
    print(f"  {'─'*4}  {'─'*30}  {'─'*8}  {'─'*16}")
    for c in chats:
        print(f"  {c['id']:<4}  {c['name']:<30}  {c['message_count']:>8,}  {c['last_message_at'] or '—'}")
    print()


def rename_chat(old_name: str, new_name: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """Rename *old_name* to *new_name*."""
    init_db(db_path)
    if _db_rename_chat(old_name, new_name, db_path):
        print(f'✅ Renamed "{old_name}" → "{new_name}"')
    else:
        print(f'Error: no chat named "{old_name}" found.', file=sys.stderr)
        sys.exit(1)


def delete_chat(name: str, db_path: str = DEFAULT_DB_PATH, yes: bool = False) -> None:
    """Delete *name* and all its messages and resources after confirmation."""
    init_db(db_path)
    chat = get_chat_by_name(name, db_path)
    if not chat:
        print(f'Error: no chat named "{name}" found.', file=sys.stderr)
        sys.exit(1)

    print(f'\n  ⚠  DELETE CHAT: "{name}"')
    print(f"  This will permanently delete {chat['message_count']:,} messages and all associated resources.")
    print()
    if not _confirm("Confirm? [y/N]: ", yes=yes):
        print("Aborted.")
        return

    _db_delete_chat(name, db_path)
    print(f'✅ Deleted chat "{name}".')


def export(
    output: str = "Extracted_Resources.xlsx",
    db_path: str = DEFAULT_DB_PATH,
    chat_name: str | None = None,
) -> None:
    """Regenerate the Excel file from existing DB data without re-importing."""
    init_db(db_path)
    chat_id: int | None = None
    final_output = output
    if chat_name:
        chat = get_chat_by_name(chat_name, db_path)
        if not chat:
            print(f'Error: no chat named "{chat_name}" found.', file=sys.stderr)
            sys.exit(1)
        chat_id = chat["id"]
        resources_dir = os.path.abspath(os.path.join("resources", chat["name"]))
        os.makedirs(resources_dir, exist_ok=True)
        final_output = os.path.join(resources_dir, os.path.basename(output))
    total = generate_excel(final_output, db_path=db_path, chat_id=chat_id)
    print(f"✅ Exported {total} resources to {final_output}")

