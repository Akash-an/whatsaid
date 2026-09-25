"""CLI entry point for whatsaid.

Usage:
    whatsaid run <file>              [--chat NAME] [--out FILE] [--db PATH] [--yes]
    whatsaid chats                   [--db PATH]
    whatsaid rename-chat <old> <new> [--db PATH]
    whatsaid delete-chat <name>      [--db PATH] [--yes]
    whatsaid export                  [--chat NAME] [--out FILE] [--db PATH]
"""

from __future__ import annotations

import argparse
import sys

from .core.pipeline import (
    delete_chat,
    export,
    list_chats,
    rename_chat,
    run,
)

_DEFAULT_DB = "data/resources.db"
_DEFAULT_OUT = "Extracted_Resources.xlsx"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whatsaid",
        description="WhatsApp Chat Information Extractor",
    )
    sub = parser.add_subparsers(dest="command")

    # ---- run ------------------------------------------------------------
    p_run = sub.add_parser("run", help="Import or append a WhatsApp chat export")
    p_run.add_argument("file", help="Path to .txt or .zip WhatsApp export")
    p_run.add_argument("--chat", metavar="NAME", help="Chat name (skips the prompt)")
    p_run.add_argument("--out", default=_DEFAULT_OUT, metavar="FILE", help="Output Excel file")
    p_run.add_argument("--db", default=_DEFAULT_DB, metavar="PATH", help="SQLite database path")
    p_run.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # ---- chats ----------------------------------------------------------
    p_chats = sub.add_parser("chats", help="List all known chats")
    p_chats.add_argument("--db", default=_DEFAULT_DB, metavar="PATH")

    # ---- rename-chat ----------------------------------------------------
    p_rename = sub.add_parser("rename-chat", help="Rename a chat")
    p_rename.add_argument("old_name", help="Current chat name")
    p_rename.add_argument("new_name", help="New chat name")
    p_rename.add_argument("--db", default=_DEFAULT_DB, metavar="PATH")

    # ---- delete-chat ----------------------------------------------------
    p_delete = sub.add_parser("delete-chat", help="Delete a chat and all its data")
    p_delete.add_argument("name", help="Chat name to delete")
    p_delete.add_argument("--db", default=_DEFAULT_DB, metavar="PATH")
    p_delete.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    # ---- export ---------------------------------------------------------
    p_export = sub.add_parser("export", help="Re-export Excel from existing DB data")
    p_export.add_argument("--chat", metavar="NAME", help="Export only this chat")
    p_export.add_argument("--out", default=_DEFAULT_OUT, metavar="FILE")
    p_export.add_argument("--db", default=_DEFAULT_DB, metavar="PATH")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == "run":
            run(args.file, output=args.out, db_path=args.db, chat_name=args.chat, yes=args.yes)
        elif args.command == "chats":
            list_chats(db_path=args.db)
        elif args.command == "rename-chat":
            rename_chat(args.old_name, args.new_name, db_path=args.db)
        elif args.command == "delete-chat":
            delete_chat(args.name, db_path=args.db, yes=args.yes)
        elif args.command == "export":
            export(output=args.out, db_path=args.db, chat_name=args.chat)
        else:
            parser.print_help()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
