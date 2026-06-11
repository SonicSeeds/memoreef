from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .bookmarks import parse_bookmarks_html, write_bookmarks_to_vault


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memoreef",
        description="MemoReef: import browser bookmarks into an Obsidian-ready local source reef.",
    )
    parser.add_argument("--version", action="version", version=f"MemoReef {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    import_cmd = sub.add_parser("import", help="Import browser bookmark HTML into Markdown Drops.")
    import_cmd.add_argument("bookmarks", type=Path, help="Browser bookmark export HTML file.")
    import_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    import_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    import_cmd.add_argument("--limit", type=int, default=None, help="Only import the first N bookmarks. Useful for tests.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "import":
        bookmarks = parse_bookmarks_html(args.bookmarks)
        if args.limit is not None:
            bookmarks = bookmarks[: args.limit]
        written = write_bookmarks_to_vault(bookmarks, args.vault, args.root)
        print(f"Imported {len(written)} Drops into {Path(args.vault).expanduser().resolve() / args.root}")
        if written:
            print(f"First Drop: {written[0]}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
