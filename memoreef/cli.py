from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from . import __version__
from .bookmarks import (
    Bookmark,
    markdown_drop_to_review_item,
    parse_bookmarks_html,
    parse_links_csv,
    parse_links_text,
    write_bookmarks_to_vault,
)


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


def add_vault_import_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    command.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    command.add_argument("--allow-duplicates", action="store_true", help="Write duplicate URLs instead of skipping them.")


def import_bookmarks(
    bookmarks: list[Bookmark],
    source: Path,
    vault: Path,
    root: str,
    allow_duplicates: bool,
    limit: int | None = None,
) -> list[Path]:
    parsed_count = len(bookmarks)
    if limit is not None:
        bookmarks = bookmarks[:limit]
    written = write_bookmarks_to_vault(bookmarks, vault, root, allow_duplicates=allow_duplicates)
    skipped_duplicates = 0 if allow_duplicates else len(bookmarks) - len(written)
    write_import_log(
        vault,
        root,
        source,
        {
            "vault": vault.expanduser().resolve(),
            "root": root,
            "limit": limit,
            "allow_duplicates": allow_duplicates,
        },
        parsed_count,
        len(written),
        skipped_duplicates,
        [],
    )
    return written


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")


def export_review_session(vault: Path, root: str = "MemoReef", output: Path | None = None) -> Path:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    drops = []
    if drops_dir.exists():
        for path in sorted(drops_dir.rglob("*.md")):
            drops.append(markdown_drop_to_review_item(path, vault_path))
    drops.sort(key=lambda drop: (drop.get("status") != "drift", str(drop.get("path", ""))))

    if output is None:
        output = vault_path / root / "review-sessions" / f"{timestamp_for_filename()}-review-session.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    drift_count = sum(1 for drop in drops if drop.get("status") == "drift")
    payload = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "stats": {
            "total": len(drops),
            "drift": drift_count,
        },
        "drops": drops,
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memoreef",
        description="MemoReef: import browser bookmarks into an Obsidian-ready local source reef.",
    )
    parser.add_argument("--version", action="version", version=f"MemoReef {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    import_cmd = sub.add_parser("import", help="Import browser bookmark HTML into Markdown Drops.")
    import_cmd.add_argument("bookmarks", type=Path, help="Browser bookmark export HTML file.")
    import_cmd.add_argument("--limit", type=int, default=None, help="Only import the first N bookmarks. Useful for tests.")
    add_vault_import_options(import_cmd)

    import_links_cmd = sub.add_parser("import-links", help="Import a plain text URL list into Markdown Drops.")
    import_links_cmd.add_argument("links", type=Path, help="Text file with one URL per line.")
    add_vault_import_options(import_links_cmd)

    import_csv_cmd = sub.add_parser("import-csv", help="Import CSV links into Markdown Drops.")
    import_csv_cmd.add_argument("csv", type=Path, help="CSV file with title,url,source,tags columns.")
    add_vault_import_options(import_csv_cmd)

    inspect_cmd = sub.add_parser("inspect", help="Inspect a browser bookmark HTML export without writing files.")
    inspect_cmd.add_argument("bookmarks", type=Path, help="Browser bookmark export HTML file.")

    review_cmd = sub.add_parser("export-review-session", help="Export Markdown Drops to review-session JSON.")
    review_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    review_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    review_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "import":
        bookmarks = parse_bookmarks_html(args.bookmarks)
        written = import_bookmarks(bookmarks, args.bookmarks, args.vault, args.root, args.allow_duplicates, args.limit)
        print(f"Imported {len(written)} Drops into {Path(args.vault).expanduser().resolve() / args.root}")
        if written:
            print(f"First Drop: {written[0]}")
        return 0

    if args.command == "import-links":
        written = import_bookmarks(parse_links_text(args.links), args.links, args.vault, args.root, args.allow_duplicates)
        print(f"Imported {len(written)} Drops into {Path(args.vault).expanduser().resolve() / args.root}")
        if written:
            print(f"First Drop: {written[0]}")
        return 0

    if args.command == "import-csv":
        written = import_bookmarks(parse_links_csv(args.csv), args.csv, args.vault, args.root, args.allow_duplicates)
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

    if args.command == "export-review-session":
        output = export_review_session(args.vault, args.root, args.output)
        print(f"Exported review session to {output}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
