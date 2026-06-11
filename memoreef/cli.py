from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from . import __version__
from .bookmarks import Bookmark, parse_bookmarks_html, write_bookmarks_to_vault


def top_level_folder_counts(bookmarks: list[Bookmark]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bookmark in bookmarks:
        folder = bookmark.folders[0] if bookmark.folders else "Unfiled"
        counts[folder] = counts.get(folder, 0) + 1
    return counts


def write_import_log(
    vault: Path,
    root: str,
    source: Path,
    options: dict[str, object],
    parsed_count: int,
    written_count: int,
    skipped_duplicate_count: int,
    errors_warnings: list[str] | None = None,
) -> Path:
    imports_dir = vault.expanduser().resolve() / root / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = imports_dir / f"{timestamp}-import.md"
    messages = errors_warnings or []

    lines = [
        "# MemoReef Import Log",
        "",
        f"- Source file: {source.expanduser().resolve()}",
        "- Command options:",
    ]
    for key, value in options.items():
        lines.append(f"  - {key}: {value}")
    lines.extend(
        [
            f"- Parsed bookmark count: {parsed_count}",
            f"- Written Drop count: {written_count}",
            f"- Skipped duplicate count: {skipped_duplicate_count}",
            "- Errors/warnings:",
        ]
    )
    if messages:
        for message in messages:
            lines.append(f"  - {message}")
    else:
        lines.append("  - none")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


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
    import_cmd.add_argument("--allow-duplicates", action="store_true", help="Write duplicate URLs instead of skipping them.")

    inspect_cmd = sub.add_parser("inspect", help="Inspect a browser bookmark HTML export without writing files.")
    inspect_cmd.add_argument("bookmarks", type=Path, help="Browser bookmark export HTML file.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "import":
        bookmarks = parse_bookmarks_html(args.bookmarks)
        parsed_count = len(bookmarks)
        if args.limit is not None:
            bookmarks = bookmarks[: args.limit]
        written = write_bookmarks_to_vault(bookmarks, args.vault, args.root, allow_duplicates=args.allow_duplicates)
        skipped_duplicates = 0 if args.allow_duplicates else len(bookmarks) - len(written)
        write_import_log(
            args.vault,
            args.root,
            args.bookmarks,
            {
                "vault": Path(args.vault).expanduser().resolve(),
                "root": args.root,
                "limit": args.limit,
                "allow_duplicates": args.allow_duplicates,
            },
            parsed_count,
            len(written),
            skipped_duplicates,
            [],
        )
        print(f"Imported {len(written)} Drops into {Path(args.vault).expanduser().resolve() / args.root}")
        if written:
            print(f"First Drop: {written[0]}")
        return 0

    if args.command == "inspect":
        bookmarks = parse_bookmarks_html(args.bookmarks)
        counts = top_level_folder_counts(bookmarks)
        print(f"Total bookmarks: {len(bookmarks)}")
        print("Top-level folders:")
        for folder, count in counts.items():
            print(f"- {folder}: {count}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
