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
    update_markdown_frontmatter,
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


def load_drop_items(vault: Path, root: str = "MemoReef") -> list[dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    drops = []
    if drops_dir.exists():
        for path in sorted(drops_dir.rglob("*.md")):
            drops.append(markdown_drop_to_review_item(path, vault_path))
    return drops


def review_decision_fields(decision: str) -> dict[str, object] | None:
    if decision == "sink":
        return {"status": "discarded", "pearl": False}
    if decision == "keep":
        return {"status": "reef", "pearl": False}
    if decision == "pearl":
        return {"status": "reef", "pearl": True}
    return None


def apply_review_decisions(
    vault: Path,
    decisions: Path,
    root: str = "MemoReef",
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = (vault_path / root / "Drops").resolve()
    payload = json.loads(decisions.expanduser().read_text(encoding="utf-8"))
    reviewed_at = payload.get("reviewed_at") or utc_now_iso()
    decision_items = payload.get("decisions")

    warnings: list[str] = []
    updated = 0
    skipped = 0

    if not isinstance(decision_items, list):
        return 0, 1, ["decisions must be a list"]

    for index, item in enumerate(decision_items, start=1):
        if not isinstance(item, dict):
            skipped += 1
            warnings.append(f"decision {index}: malformed decision")
            continue

        raw_path = item.get("path")
        raw_decision = item.get("decision")
        fields = review_decision_fields(str(raw_decision or ""))
        if not isinstance(raw_path, str) or not raw_path.strip():
            skipped += 1
            warnings.append(f"decision {index}: missing path")
            continue
        if fields is None:
            skipped += 1
            warnings.append(f"{raw_path}: unsupported decision")
            continue

        relative_path = Path(raw_path)
        if relative_path.is_absolute():
            skipped += 1
            warnings.append(f"{raw_path}: path must be relative to the vault")
            continue

        target = (vault_path / relative_path).resolve()
        try:
            target.relative_to(drops_dir)
        except ValueError:
            skipped += 1
            warnings.append(f"{raw_path}: path is outside MemoReef Drops")
            continue

        if target.suffix != ".md":
            skipped += 1
            warnings.append(f"{raw_path}: not a Markdown Drop")
            continue
        if not target.exists():
            skipped += 1
            warnings.append(f"{raw_path}: file not found")
            continue

        fields["triaged_at"] = str(reviewed_at)
        if not dry_run:
            content = target.read_text(encoding="utf-8", errors="replace")
            target.write_text(update_markdown_frontmatter(content, fields), encoding="utf-8")
        updated += 1

    return updated, skipped, warnings


AGENT_FINISH_INSTRUCTIONS = [
    "Use pearl decisions as strongest positive taste examples.",
    "Use keep decisions as acceptable but ordinary examples.",
    "Use sink decisions as negative examples.",
    "For remaining Drops, propose status, pearl, tags, priority, and note location in a later task.",
    "Do not delete or move files without explicit user approval.",
]


def review_taste_example(drop: dict[str, object]) -> dict[str, object]:
    return {
        "id": drop.get("id", ""),
        "path": drop.get("path", ""),
        "title": drop.get("title", ""),
        "url": drop.get("url", ""),
        "summary": drop.get("summary", ""),
        "tags": drop.get("tags", []),
        "folders": drop.get("folders", []),
    }


def build_agent_finish_plan(
    vault: Path,
    decisions: Path,
    root: str = "MemoReef",
    output: Path | None = None,
) -> tuple[Path, dict[str, object], list[str]]:
    vault_path = vault.expanduser().resolve()
    drops = load_drop_items(vault_path, root)
    drops_by_path = {str(drop.get("path", "")): drop for drop in drops}
    decisions_path = decisions.expanduser().resolve()
    payload = json.loads(decisions_path.read_text(encoding="utf-8"))
    decision_items = payload.get("decisions")

    taste_examples: dict[str, list[dict[str, object]]] = {"pearl": [], "keep": [], "sink": []}
    reviewed_paths: set[str] = set()
    warnings: list[str] = []

    if not isinstance(decision_items, list):
        warnings.append("decisions must be a list")
        decision_items = []

    for index, item in enumerate(decision_items, start=1):
        if not isinstance(item, dict):
            warnings.append(f"decision {index}: malformed decision")
            continue

        raw_path = item.get("path")
        raw_decision = item.get("decision")
        if not isinstance(raw_path, str) or not raw_path.strip():
            warnings.append(f"decision {index}: missing path")
            continue
        if not isinstance(raw_decision, str) or raw_decision not in taste_examples:
            warnings.append(f"{raw_path}: unsupported decision")
            continue

        reviewed_paths.add(raw_path)
        drop = drops_by_path.get(raw_path)
        if drop is None:
            warnings.append(f"{raw_path}: file not found")
            continue
        taste_examples[raw_decision].append(review_taste_example(drop))

    remaining_drops = [drop for drop in drops if str(drop.get("path", "")) not in reviewed_paths]
    reviewed_count = sum(len(items) for items in taste_examples.values())

    if output is None:
        output = vault_path / root / "agent-plans" / f"{timestamp_for_filename()}-agent-finish-plan.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    plan = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "decisions_source": str(decisions_path),
        "summary": {
            "reviewed": reviewed_count,
            "remaining": len(remaining_drops),
            "pearls": len(taste_examples["pearl"]),
            "kept": len(taste_examples["keep"]),
            "sunk": len(taste_examples["sink"]),
        },
        "taste_examples": taste_examples,
        "remaining_drops": remaining_drops,
        "agent_instructions": AGENT_FINISH_INSTRUCTIONS,
        "warnings": warnings,
    }
    output.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return output, plan, warnings


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

    apply_cmd = sub.add_parser("apply-review-decisions", help="Apply Review Mode decision JSON to Markdown Drops.")
    apply_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    apply_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    apply_cmd.add_argument("--decisions", type=Path, required=True, help="Review decisions JSON exported from Review Mode.")
    apply_cmd.add_argument("--dry-run", action="store_true", help="Preview updates without modifying Markdown files.")

    plan_cmd = sub.add_parser("plan-agent-finish", help="Create an agent finish plan for unreviewed Drops.")
    plan_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    plan_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    plan_cmd.add_argument("--decisions", type=Path, required=True, help="Review decisions JSON exported from Review Mode.")
    plan_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")

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

    if args.command == "apply-review-decisions":
        updated, skipped, warnings = apply_review_decisions(args.vault, args.decisions, args.root, args.dry_run)
        if args.dry_run:
            print("Dry run review decisions:")
            print(f"- would update: {updated}")
        else:
            print("Applied review decisions:")
            print(f"- updated: {updated}")
        print(f"- skipped: {skipped}")
        print(f"- warnings: {len(warnings)}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "plan-agent-finish":
        output, plan, warnings = build_agent_finish_plan(args.vault, args.decisions, args.root, args.output)
        summary = plan.get("summary", {})
        reviewed = summary.get("reviewed", 0) if isinstance(summary, dict) else 0
        remaining = summary.get("remaining", 0) if isinstance(summary, dict) else 0
        print("Created agent finish plan:")
        print(f"- reviewed examples: {reviewed}")
        print(f"- remaining drops: {remaining}")
        print(f"- warnings: {len(warnings)}")
        print(f"- output: {output}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
