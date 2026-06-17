from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import escape as html_escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit


def write_optional_qr_png(url: str, output: Path) -> tuple[Path | None, str | None]:
    """Write a QR PNG when the optional qrcode package is installed."""
    try:
        import qrcode  # type: ignore[import-not-found]
    except ImportError as error:
        return None, f"QR PNG skipped: optional Python package 'qrcode' is not installed ({error})."
    output.parent.mkdir(parents=True, exist_ok=True)
    image = qrcode.make(url)
    with output.open("wb") as file:
        image.save(file)
    return output, None

from . import __version__
from .bookmarks import (
    Bookmark,
    canonicalize_url,
    markdown_drop_to_review_item,
    parse_markdown_frontmatter,
    parse_bookmarks_html,
    parse_links_csv,
    parse_links_text,
    update_markdown_frontmatter,
    write_bookmarks_to_vault,
)
from .documents import parse_documents


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


DEMO_REVIEWED_AT = "2026-06-12T09:00:00Z"


def demo_bookmarks() -> list[Bookmark]:
    return [
        Bookmark(
            "Local AI agent playbook for research teams",
            "https://example.com/ai-agents/local-agent-playbook",
            source="memo-demo",
            status="reef",
            pearl=True,
            folders=["Research", "AI Agents"],
            tags=["ai-agents", "local-first", "workflow"],
            projects=["AI Agents"],
            shoals=["Automation"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Agent workflow checklist for saved links",
            "https://example.com/ai-agents/workflow-checklist?utm_source=newsletter",
            source="memo-demo",
            status="drift",
            folders=["Research", "AI Agents"],
            tags=["ai-agents", "review", "checklist"],
        ),
        Bookmark(
            "How small teams build local knowledge bases",
            "https://example.com/knowledge/local-markdown-archive",
            source="memo-demo",
            status="reef",
            folders=["Knowledge Management"],
            tags=["markdown", "local-first", "archive"],
            projects=["Local Knowledge Base"],
            shoals=["Markdown Archive"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Markdown archive patterns that survive app churn",
            "https://example.com/knowledge/markdown-archive-patterns",
            source="memo-demo",
            status="deep",
            pearl=True,
            folders=["Knowledge Management"],
            tags=["markdown", "durability", "notes"],
            projects=["Local Knowledge Base"],
            shoals=["Markdown Archive"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Design systems bookmark audit",
            "https://design.example.com/articles/bookmark-audit",
            source="memo-demo",
            status="reef",
            folders=["Product Design"],
            tags=["design-systems", "audit"],
            projects=["Product Research"],
            shoals=["Design Systems"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Design system component checklist",
            "https://design.example.com/articles/component-checklist",
            source="memo-demo",
            status="drift",
            folders=["Product Design"],
            tags=["design-systems", "checklist"],
        ),
        Bookmark(
            "SQLite full text search notes",
            "https://engineering.example.net/sqlite/full-text-search",
            source="memo-demo",
            status="drift",
            folders=["Engineering"],
            tags=["search", "sqlite", "local-first"],
        ),
        Bookmark(
            "Searchable personal archives with plain files",
            "https://engineering.example.net/search/plain-file-archives",
            source="memo-demo",
            status="deep",
            folders=["Engineering"],
            tags=["search", "archive", "markdown"],
            projects=["Local Knowledge Base"],
            shoals=["Search"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Noise article with vague productivity tricks",
            "https://clickbait.example.org/productivity/one-weird-trick",
            source="memo-demo",
            status="discarded",
            folders=["Inbox"],
            tags=["productivity", "noise"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Outdated launch rumor",
            "https://rumors.example.org/launch/old-rumor",
            source="memo-demo",
            status="discarded",
            folders=["Inbox"],
            tags=["rumor", "stale"],
            triaged_at=DEMO_REVIEWED_AT,
        ),
        Bookmark(
            "Local AI agent playbook for research teams duplicate",
            "https://example.com/ai-agents/local-agent-playbook?utm_medium=social",
            source="memo-demo",
            status="drift",
            folders=["Inbox"],
            tags=["ai-agents", "duplicate"],
        ),
        Bookmark(
            "MemoReef pricing research spreadsheet",
            "file:///Users/demo/research/pricing-links.csv",
            source="memo-demo",
            status="drift",
            folders=["Inbox"],
            tags=["pricing", "local-file"],
        ),
    ]


DEMO_METADATA: dict[str, dict[str, str]] = {
    "Local AI agent playbook for research teams": {
        "hostname": "example.com",
        "page_title": "Local AI agent playbook for research teams",
        "page_description": "A practical guide to turning scattered research links into local agent-ready context.",
        "canonical_url": "https://example.com/ai-agents/local-agent-playbook",
    },
    "Agent workflow checklist for saved links": {
        "hostname": "example.com",
        "page_title": "Agent workflow checklist for saved links",
        "page_description": "A checklist for reviewing saved AI workflow links before handing them to an agent.",
        "canonical_url": "https://example.com/ai-agents/workflow-checklist",
    },
    "How small teams build local knowledge bases": {
        "hostname": "example.com",
        "page_title": "How small teams build local knowledge bases",
        "page_description": "Why Markdown vaults make team research portable, searchable, and durable.",
        "canonical_url": "https://example.com/knowledge/local-markdown-archive",
    },
    "Markdown archive patterns that survive app churn": {
        "hostname": "example.com",
        "page_title": "Markdown archive patterns that survive app churn",
        "page_description": "Patterns for storing useful links and notes in plain files that outlive SaaS tools.",
        "canonical_url": "https://example.com/knowledge/markdown-archive-patterns",
    },
    "Design systems bookmark audit": {
        "hostname": "design.example.com",
        "page_title": "Design systems bookmark audit",
        "page_description": "A method for separating durable design system references from transient inspiration.",
        "canonical_url": "https://design.example.com/articles/bookmark-audit",
    },
    "Design system component checklist": {
        "hostname": "design.example.com",
        "page_title": "Design system component checklist",
        "page_description": "Reusable criteria for evaluating component libraries and design system references.",
        "canonical_url": "https://design.example.com/articles/component-checklist",
    },
    "SQLite full text search notes": {
        "hostname": "engineering.example.net",
        "page_title": "SQLite full text search notes",
        "page_description": "Implementation notes for fast local search over Markdown Drops.",
        "canonical_url": "https://engineering.example.net/sqlite/full-text-search",
    },
    "Searchable personal archives with plain files": {
        "hostname": "engineering.example.net",
        "page_title": "Searchable personal archives with plain files",
        "page_description": "How plain files and local indexes keep saved research usable without a backend.",
        "canonical_url": "https://engineering.example.net/search/plain-file-archives",
    },
}


DEMO_SUMMARIES: dict[str, str] = {
    "Local AI agent playbook for research teams": "A strong Pearl example: local-first AI agent workflows, research triage, and durable handoff context.",
    "Agent workflow checklist for saved links": "A messy inbox Drop that looks related to the AI Agents project but has not been reviewed yet.",
    "How small teams build local knowledge bases": "A kept reference about using Markdown to make saved links portable and searchable.",
    "Markdown archive patterns that survive app churn": "A deep Pearl for the long-term archive: plain Markdown, stable URLs, and future agent readability.",
    "Design systems bookmark audit": "A curated product research source about cleaning up design system bookmarks.",
    "Design system component checklist": "An unreviewed same-domain candidate that garden suggestions can connect to Product Research.",
    "SQLite full text search notes": "A technical Drop about local search that should remain available without a backend.",
    "Searchable personal archives with plain files": "A deep reference about search, plain files, and local archive durability.",
    "Noise article with vague productivity tricks": "A discarded example showing that MemoReef tracks negative taste as well as good sources.",
    "Outdated launch rumor": "A discarded stale link that should not pollute agent context.",
    "Local AI agent playbook for research teams duplicate": "A duplicate-looking Drift Drop saved from another channel, useful for duplicate reports.",
    "MemoReef pricing research spreadsheet": "A local file URL representing private research that must never leave the machine.",
}


def replace_markdown_section(body: str, heading: str, replacement: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub(rf"\1\n{replacement.strip()}\n\n", body)


def enrich_demo_drop(path: Path, vault: Path) -> None:
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = parse_markdown_frontmatter(content)
    title = str(frontmatter.get("title") or path.stem)
    updates: dict[str, object] = {
        "demo": True,
        "metadata_status": "demo",
        "metadata_refreshed_at": DEMO_REVIEWED_AT,
    }
    updates.update(DEMO_METADATA.get(title, {}))
    summary = DEMO_SUMMARIES.get(title, "A sample saved link in the MemoReef demo vault.")
    body = replace_markdown_section(body, "Summary", summary)
    body = replace_markdown_section(
        body,
        "Notes",
        "\n".join(
            [
                "- Demo Drop: realistic but fictional source.",
                "- Shows how saved links become searchable Markdown with review state.",
                "- Safe to inspect locally; no network or AI call is required.",
            ]
        ),
    )
    body = replace_markdown_section(
        body,
        "Agent Brief",
        "\n".join(
            [
                f"- Status: {frontmatter.get('status', 'drift')}",
                f"- Pearl: {'yes' if frontmatter.get('pearl') is True else 'no'}",
                "- Use the frontmatter, summary, tags, projects, and shoals as local context.",
                f"- Relative path: {path.resolve().relative_to(vault.resolve()).as_posix()}",
            ]
        ),
    )
    path.write_text(update_markdown_frontmatter(f"---\n---\n{body}", {**frontmatter, **updates}), encoding="utf-8")


def write_demo_decisions(vault: Path, root: str, review_session: Path) -> Path:
    drops = load_drop_items(vault, root)
    decisions: list[dict[str, str]] = []
    wanted = {
        "Local AI agent playbook for research teams": "pearl",
        "How small teams build local knowledge bases": "keep",
        "Noise article with vague productivity tricks": "sink",
    }
    for drop in drops:
        title = str(drop.get("title") or "")
        decision = wanted.get(title)
        if decision:
            decisions.append({"path": str(drop.get("path") or ""), "decision": decision})
    path = vault / "memoreef-demo-review-decisions.json"
    payload = {
        "version": 1,
        "reviewed_at": DEMO_REVIEWED_AT,
        "review_session": str(review_session),
        "decisions": decisions,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def cleanup_previous_demo_files(vault: Path, root: str) -> None:
    root_path = vault / root
    drops_dir = root_path / "Drops"
    if drops_dir.exists():
        for path in sorted(drops_dir.glob("*.md")):
            frontmatter, _body = parse_markdown_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            if frontmatter.get("demo") is True:
                path.unlink()

    known_files = [
        root_path / "DEMO_README.md",
        root_path / "app" / "index.html",
        root_path / "app" / "library.html",
        root_path / "app" / "tour.html",
        root_path / "app" / "review.html",
        root_path / "app" / "reports.html",
        root_path / "app" / "briefs.html",
        root_path / "app" / "pilot.html",
        root_path / "PILOT_README.md",
        root_path / "review-sessions" / "demo-review-session.json",
        root_path / "reports" / "demo-duplicate-report.json",
        root_path / "reports" / "demo-garden-suggestions.json",
        root_path / "search" / "demo-search-results.json",
        root_path / "briefs" / "demo-ai-agents-project-brief.md",
        root_path / "agent-plans" / "demo-agent-finish-plan.json",
        root_path / "agent-plans" / "demo-agent-proposals.json",
        vault / "memoreef-demo-review-decisions.json",
    ]
    for path in known_files:
        if path.exists() and path.is_file():
            path.unlink()
    app_drops = root_path / "app" / "drops"
    if app_drops.exists():
        for path in sorted(app_drops.glob("*.html")):
            path.unlink()


def demo_readme_text(vault: Path, root: str, artifacts: dict[str, Path]) -> str:
    root_path = vault / root
    rel = {name: path.resolve().relative_to(vault.resolve()).as_posix() for name, path in artifacts.items()}
    return f"""# MemoReef Demo Vault

MemoReef is a local-first Markdown archive for saved links and bookmarks. It turns a messy browser backlog into plain-text Drops with review status, tags, projects, shoals, metadata, reports, search output, and agent-readable context.

## What problem this solves

Saved links usually become a junk drawer: duplicates, old rumors, private files, good references, and half-reviewed research all sit together. MemoReef keeps that material local, makes it reviewable, and records enough structure that a human or coding agent can understand what is worth keeping.

## Open this first

Open the generated product tour first:

```bash
open {rel["pilot"]}
open {rel["tour"]}
```

Then open the dashboard, local library, review launcher, reports, briefs, pilot checklist, and example Drop detail pages:

```bash
open {rel["dashboard"]}
open {root}/app/pilot.html
open {root}/app/library.html
open {root}/app/review.html
open {root}/app/reports.html
open {root}/app/briefs.html
open {root}/app/drops
```

These pages are static files. There is no backend, account, network call, or AI call.

## What is in this demo

- At least 12 realistic sample Drops under `{root}/Drops`.
- Mixed statuses: `drift`, `reef`, `deep`, and `discarded`.
- Pearl examples for high-value saved links.
- Projects, shoals, folders, tags, hostnames, titles, descriptions, and canonical URLs.
- Duplicate and same-domain examples for local reports.
- A review session JSON: `{rel["review_session"]}`.
- A duplicate report: `{rel["duplicate_report"]}`.
- Garden suggestions: `{rel["garden_suggestions"]}`.
- A search result: `{rel["search_results"]}`.
- A project brief for agent handoff: `{rel["project_brief"]}`.
- Static app pages for dashboard, tour, library search, Review Mode instructions, reports, briefs, and one generated detail page per Drop.
- A pilot checklist page and Markdown checklist: `{rel["pilot"]}`, `{root}/PILOT_README.md`.
- A demo review-decisions file and agent finish artifacts: `{rel["decisions"]}`, `{rel["agent_plan"]}`, `{rel["agent_proposals"]}`.

## Local workflow

1. Import: real usage starts with `import`, `import-links`, or `import-csv`. This demo preloads sample Drops so you can inspect the result immediately.
2. Review: run `export-review-session` and open Review Mode to mark Drops as keep, Pearl, or sink.
3. Agent finish: exported decisions become taste examples for `plan-agent-finish` and `draft-agent-proposals`.
4. Search/library: run `search-library` to create local JSON search results, then open `MemoReef/app/library.html`.
5. Brief: run `brief --project "AI Agents"` to turn selected Drops into a Markdown project brief with source URLs and agent handoff rules.

## Why local Markdown matters

The core archive is readable without MemoReef. Each Drop is a Markdown file with frontmatter, a source URL, a summary, notes, and an agent brief. That means your saved research can be searched, backed up, synced, edited, reviewed, or handed to another local tool without exporting from a hosted service.

## Prototype vs production-ready

This demo is production-shaped but still a prototype. The sample data is fictional, metadata is prefilled instead of fetched, and the app is static HTML. The local file workflow, Markdown Drops, review sessions, reports, garden suggestions, search results, and agent finish artifacts are real CLI outputs generated without network access.

Generated vault root: `{root_path}`
"""


def create_demo_vault(output: Path, root: str = "MemoReef") -> dict[str, object]:
    vault = output.expanduser().resolve()
    vault.mkdir(parents=True, exist_ok=True)
    cleanup_previous_demo_files(vault, root)
    written = write_bookmarks_to_vault(demo_bookmarks(), vault, root, allow_duplicates=True)
    for path in written:
        enrich_demo_drop(path, vault)

    root_path = vault / root
    review_session, review_payload = export_review_session(
        vault,
        root,
        root_path / "review-sessions" / "demo-review-session.json",
        filters=default_review_filters(status=["drift"], limit=8),
    )
    duplicate_report, duplicate_payload = create_duplicate_report(vault, root, root_path / "reports" / "demo-duplicate-report.json")
    garden_suggestions, garden_payload = create_garden_suggestions_report(vault, root, root_path / "reports" / "demo-garden-suggestions.json")
    search_results, search_payload = search_library(
        vault,
        "agent workflow markdown search",
        root,
        root_path / "search" / "demo-search-results.json",
        filters=default_review_filters(limit=10),
    )
    project_brief, brief_payload = create_project_brief(
        vault,
        root,
        root_path / "briefs" / "demo-ai-agents-project-brief.md",
        filters=default_review_filters(project=["AI Agents"], limit=8),
    )
    decisions = write_demo_decisions(vault, root, review_session)
    agent_plan, plan_payload, _plan_warnings = build_agent_finish_plan(
        vault,
        decisions,
        root,
        root_path / "agent-plans" / "demo-agent-finish-plan.json",
    )
    agent_proposals, proposals_payload, _proposal_warnings = draft_agent_proposals(
        agent_plan,
        root_path / "agent-plans" / "demo-agent-proposals.json",
    )
    pilot_readme = write_pilot_readme(
        vault,
        root,
        {
            "source_kind": "demo",
            "source_path": vault / root / "DEMO_README.md",
            "written_count": len(written),
            "review_limit": 8,
            "review_session": review_session,
            "duplicate_report": duplicate_report,
            "app_dashboard": root_path / "app" / "index.html",
            "app_pilot": root_path / "app" / "pilot.html",
            "commands": [
                f"python3 -m memoreef.cli demo --output {vault}",
                f"python3 -m memoreef.cli export-review-session --vault {vault} --root {root} --status drift --limit 8",
                f"python3 -m memoreef.cli duplicate-report --vault {vault} --root {root}",
                f"python3 -m memoreef.cli app --vault {vault} --root {root}",
            ],
            "skip_reports": False,
        },
    )
    dashboard = generate_app_dashboard(vault, root)
    tour = root_path / "app" / "tour.html"
    pilot = root_path / "app" / "pilot.html"

    artifacts = {
        "dashboard": dashboard,
        "tour": tour,
        "pilot": pilot,
        "review_session": review_session,
        "duplicate_report": duplicate_report,
        "garden_suggestions": garden_suggestions,
        "search_results": search_results,
        "project_brief": project_brief,
        "decisions": decisions,
        "agent_plan": agent_plan,
        "agent_proposals": agent_proposals,
    }
    readme = vault / root / "DEMO_README.md"
    readme.write_text(demo_readme_text(vault, root, artifacts), encoding="utf-8")

    return {
        "vault": vault,
        "root": root,
        "drops": len(written),
        "review_items": review_payload["stats"]["total"],
        "duplicate_groups": duplicate_payload["summary"]["exact_url_groups"],
        "garden_suggestions": garden_payload["summary"]["suggestions"],
        "search_matches": search_payload["summary"]["matches"],
        "brief_sources": brief_payload["summary"]["sources"],
        "agent_proposals": proposals_payload["summary"]["proposed"],
        "dashboard": dashboard,
        "tour": tour,
        "pilot": pilot,
        "pilot_readme": pilot_readme,
        "readme": readme,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")


def default_review_filters(
    project: list[str] | None = None,
    shoal: list[str] | None = None,
    status: list[str] | None = None,
    tag: list[str] | None = None,
    folder: list[str] | None = None,
    hostname: list[str] | None = None,
    pearl_only: bool = False,
    exclude_status: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    return {
        "project": project or [],
        "shoal": shoal or [],
        "status": status or [],
        "tag": tag or [],
        "folder": folder or [],
        "hostname": hostname or [],
        "pearl_only": pearl_only,
        "exclude_status": exclude_status or [],
        "limit": limit,
    }


def normalized_match(value: object, accepted: list[str]) -> bool:
    if not accepted:
        return True
    return str(value).casefold() in {item.casefold() for item in accepted}


def normalized_list_match(values: object, accepted: list[str]) -> bool:
    if not accepted:
        return True
    if not isinstance(values, list):
        return False
    accepted_values = {item.casefold() for item in accepted}
    return any(str(value).casefold() in accepted_values for value in values)


def review_hostname(drop: dict[str, object]) -> str:
    hostname = str(drop.get("hostname") or "")
    if hostname:
        return hostname.lower()
    return (urlsplit(str(drop.get("url") or "")).hostname or "").lower()


def review_filter_active(filters: dict[str, object]) -> bool:
    return any(
        bool(filters.get(key))
        for key in ("project", "shoal", "status", "tag", "folder", "hostname", "pearl_only", "exclude_status", "limit")
    )


def review_filter_summary(filters: dict[str, object]) -> str:
    parts: list[str] = []
    labels = [
        ("project", "project"),
        ("shoal", "shoal"),
        ("status", "status"),
        ("tag", "tag"),
        ("folder", "folder"),
        ("hostname", "hostname"),
        ("exclude_status", "exclude-status"),
    ]
    for key, label in labels:
        values = filters.get(key)
        if isinstance(values, list) and values:
            parts.append(f"{label}={', '.join(str(value) for value in values)}")
    if filters.get("pearl_only"):
        parts.append("pearl-only=true")
    if filters.get("limit") is not None:
        parts.append(f"limit={filters['limit']}")
    return ", ".join(parts) if parts else "none"


def review_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip() and str(item).strip() != "[]"]


def search_filter_summary(filters: dict[str, object]) -> str:
    summary_filters = dict(filters)
    if summary_filters.get("limit") == 20:
        summary_filters["limit"] = None
    return review_filter_summary(summary_filters)


def search_text_tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", value.casefold()) if token]


def markdown_drop_to_filtered_review_item(path: Path, vault: Path) -> dict[str, object]:
    base = markdown_drop_to_review_item(path, vault)
    frontmatter, _body = parse_markdown_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    projects = review_list(frontmatter.get("projects"))
    shoals = review_list(frontmatter.get("shoals"))
    hostname = str(frontmatter.get("hostname") or "")
    if not hostname:
        hostname = urlsplit(str(frontmatter.get("url") or "")).hostname or ""
    base["projects"] = projects
    base["shoals"] = shoals
    base["hostname"] = hostname.lower()
    return base


def filter_values(filters: dict[str, object], key: str) -> list[str]:
    value = filters.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def review_item_matches_filters(drop: dict[str, object], filters: dict[str, object]) -> bool:
    if not normalized_list_match(drop.get("projects"), filter_values(filters, "project")):
        return False
    if not normalized_list_match(drop.get("shoals"), filter_values(filters, "shoal")):
        return False
    if not normalized_match(drop.get("status", ""), filter_values(filters, "status")):
        return False
    if not normalized_list_match(drop.get("tags"), filter_values(filters, "tag")):
        return False
    if not normalized_list_match(drop.get("folders"), filter_values(filters, "folder")):
        return False
    if not normalized_match(review_hostname(drop), filter_values(filters, "hostname")):
        return False
    if filters.get("pearl_only") and not bool(drop.get("pearl", False)):
        return False
    exclude_statuses = filter_values(filters, "exclude_status")
    if exclude_statuses and normalized_match(drop.get("status", ""), exclude_statuses):
        return False
    return True


def search_field_score(text: str, query_terms: list[str], weight: int) -> tuple[int, bool]:
    normalized = text.casefold()
    matched = sum(1 for term in query_terms if term in normalized)
    phrase_bonus = 1 if " ".join(query_terms) in normalized and len(query_terms) > 1 else 0
    return (matched + phrase_bonus) * weight, matched > 0 or phrase_bonus > 0


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def search_snippet(texts: list[str], query_terms: list[str]) -> str:
    haystack = compact_text(" ".join(text for text in texts if text))
    if not haystack:
        return ""
    lower = haystack.casefold()
    indexes = [lower.find(term) for term in query_terms if lower.find(term) >= 0]
    if not indexes:
        return haystack[:180]
    start = max(0, min(indexes) - 60)
    end = min(len(haystack), start + 180)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(haystack) else ""
    return f"{prefix}{haystack[start:end]}{suffix}"


def search_drop_item(path: Path, vault: Path) -> dict[str, object]:
    item = markdown_drop_to_filtered_review_item(path, vault)
    frontmatter, body = parse_markdown_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    item["page_description"] = str(frontmatter.get("page_description") or "")
    item["body"] = body
    return item


def markdown_section(body: str, heading: str) -> str:
    lines = body.splitlines()
    marker = f"## {heading}"
    for i, line in enumerate(lines):
        if line.strip() != marker:
            continue
        section: list[str] = []
        for section_line in lines[i + 1 :]:
            if section_line.startswith("## "):
                break
            section.append(section_line)
        return "\n".join(section).strip()
    return ""


def score_search_item(drop: dict[str, object], query_terms: list[str]) -> dict[str, object] | None:
    matched_fields: list[str] = []
    score = 0

    title_score, matched = search_field_score(str(drop.get("title") or ""), query_terms, 8)
    if matched:
        matched_fields.append("title")
    score += title_score

    for field in ("projects", "shoals", "tags", "folders"):
        values = drop.get(field, [])
        text = " ".join(str(value) for value in values) if isinstance(values, list) else ""
        field_score, matched = search_field_score(text, query_terms, 5)
        if matched:
            matched_fields.append(field)
        score += field_score

    hostname_url = f"{drop.get('hostname') or ''} {drop.get('url') or ''}"
    host_score, matched = search_field_score(hostname_url, query_terms, 3)
    if matched:
        matched_fields.extend(["hostname", "url"])
    score += host_score

    summary_text = f"{drop.get('summary') or ''} {drop.get('page_description') or ''}"
    summary_score, matched = search_field_score(summary_text, query_terms, 2)
    if matched:
        matched_fields.append("summary")
    score += summary_score

    body_score, matched = search_field_score(str(drop.get("body") or ""), query_terms, 1)
    if matched:
        matched_fields.append("body")
    score += body_score

    if score <= 0:
        return None

    return {
        "id": drop.get("id", ""),
        "path": drop.get("path", ""),
        "title": drop.get("title", ""),
        "url": drop.get("url", ""),
        "hostname": drop.get("hostname", ""),
        "status": drop.get("status", "drift"),
        "pearl": bool(drop.get("pearl", False)),
        "projects": drop.get("projects", []),
        "shoals": drop.get("shoals", []),
        "folders": drop.get("folders", []),
        "tags": drop.get("tags", []),
        "score": score,
        "matched_fields": sorted(set(matched_fields)),
        "snippet": search_snippet(
            [
                str(drop.get("title") or ""),
                str(drop.get("summary") or ""),
                str(drop.get("page_description") or ""),
                str(drop.get("body") or ""),
            ],
            query_terms,
        ),
    }


def search_library(
    vault: Path,
    query: str,
    root: str = "MemoReef",
    output: Path | None = None,
    filters: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    filters = filters or default_review_filters(limit=20)
    limit = filters.get("limit")
    if not isinstance(limit, int) or limit < 0:
        limit = 20
        filters["limit"] = limit
    query_terms = search_text_tokens(query)
    drops_dir = vault_path / root / "Drops"
    results: list[dict[str, object]] = []

    if query_terms and drops_dir.exists():
        for path in sorted(drops_dir.rglob("*.md")):
            drop = search_drop_item(path, vault_path)
            if not review_item_matches_filters(drop, filters):
                continue
            result = score_search_item(drop, query_terms)
            if result is not None:
                results.append(result)

    results.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            not bool(item.get("pearl", False)),
            str(item.get("status") or "") != "drift",
            str(item.get("path") or ""),
        )
    )
    results = results[:limit]

    if output is None:
        output = vault_path / root / "search" / f"{timestamp_for_filename()}-search-results.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "query": query,
        "filters": filters,
        "summary": {
            "matches": len(results),
            "limit": limit,
        },
        "items": results,
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output, payload


def slug_for_filename(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "sources"


def brief_item_from_drop(path: Path, vault: Path) -> dict[str, object]:
    item = search_drop_item(path, vault)
    body = str(item.get("body") or "")
    item["notes"] = markdown_section(body, "Notes")
    item["agent_brief"] = markdown_section(body, "Agent Brief")
    return item


def brief_list(values: object) -> str:
    if isinstance(values, list) and values:
        return ", ".join(str(value) for value in values)
    return "none"


def render_project_brief(vault: Path, root: str, filters: dict[str, object], drops: list[dict[str, object]]) -> str:
    created_at = utc_now_iso()
    filter_summary = review_filter_summary(filters)
    status_counts: dict[str, int] = {}
    for drop in drops:
        status = str(drop.get("status") or "drift")
        status_counts[status] = status_counts.get(status, 0) + 1
    missing_summaries = [drop for drop in drops if not str(drop.get("summary") or "").strip()]
    discarded = [drop for drop in drops if str(drop.get("status") or "") == "discarded"]

    lines = [
        "# MemoReef Project Brief",
        "",
        f"- Generated: {created_at}",
        f"- Vault: `{vault}`",
        f"- Source: `{root}/Drops`",
        f"- Applied filters: {filter_summary}",
        "",
        "## Summary counts",
        "",
        f"- Selected sources: {len(drops)}",
        f"- Pearls: {sum(1 for drop in drops if bool(drop.get('pearl', False)))}",
        f"- Missing summaries: {len(missing_summaries)}",
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"- Status `{status}`: {count}")

    lines.extend(["", "## Selected sources", ""])
    if not drops:
        lines.append("No Drops matched the applied filters.")
    for index, drop in enumerate(drops, start=1):
        pearl = "yes" if bool(drop.get("pearl", False)) else "no"
        lines.extend(
            [
                f"### {index}. {drop.get('title') or 'Untitled'}",
                "",
                f"- URL: {drop.get('url') or 'none'}",
                f"- Status: {drop.get('status') or 'drift'}",
                f"- Pearl: {pearl}",
                f"- Tags: {brief_list(drop.get('tags'))}",
                f"- Projects: {brief_list(drop.get('projects'))}",
                f"- Shoals: {brief_list(drop.get('shoals'))}",
                f"- Hostname: {drop.get('hostname') or 'none'}",
                f"- Drop path: `{drop.get('path') or ''}`",
                "",
            ]
        )
        summary = str(drop.get("summary") or "").strip()
        notes = str(drop.get("notes") or "").strip()
        agent_brief = str(drop.get("agent_brief") or "").strip()
        if summary:
            lines.extend(["Summary:", "", summary, ""])
        elif drop.get("page_description"):
            lines.extend(["Summary:", "", str(drop.get("page_description")), ""])
        else:
            lines.extend(["Summary:", "", "No summary found in this Drop.", ""])
        if notes:
            lines.extend(["Notes:", "", notes, ""])
        if agent_brief:
            lines.extend(["Drop agent brief:", "", agent_brief, ""])

    lines.extend(
        [
            "## Agent handoff",
            "",
            "- Use only the sources listed in this brief for factual claims.",
            "- Cite source URLs when making claims or recommendations.",
            "- Note gaps, uncertainty, stale sources, and missing summaries explicitly.",
            "- Do not invent claims, citations, authors, dates, quotes, or source coverage.",
            "- If the listed sources are insufficient, ask for more sources or a wider MemoReef filter.",
            "",
            "## Gaps / next review",
            "",
        ]
    )
    if not drops:
        lines.append("- No matching sources were selected; broaden filters or import/review more Drops.")
    if len(drops) < 3:
        lines.append("- Low source count; consider adding more reviewed sources before agent handoff.")
    if missing_summaries:
        titles = ", ".join(str(drop.get("title") or "Untitled") for drop in missing_summaries[:8])
        lines.append(f"- Missing summaries: {titles}.")
    if discarded:
        titles = ", ".join(str(drop.get("title") or "Untitled") for drop in discarded[:8])
        lines.append(f"- Discarded sources are included by the current filters: {titles}.")
    if not any(line.startswith("- ") for line in lines[lines.index("## Gaps / next review") + 2 :]):
        lines.append("- No obvious gaps detected from local Drop metadata.")
    return "\n".join(lines).rstrip() + "\n"


def create_project_brief(
    vault: Path,
    root: str = "MemoReef",
    output: Path | None = None,
    filters: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    filters = filters or default_review_filters()
    drops: list[dict[str, object]] = []
    if drops_dir.exists():
        for path in sorted(drops_dir.rglob("*.md")):
            drop = brief_item_from_drop(path, vault_path)
            if review_item_matches_filters(drop, filters):
                drops.append(drop)
    drops.sort(key=lambda drop: (drop.get("status") != "drift", str(drop.get("path", ""))))
    limit = filters.get("limit")
    if isinstance(limit, int) and limit >= 0:
        drops = drops[:limit]

    if output is None:
        project_values = filter_values(filters, "project")
        name = project_values[0] if project_values else "sources"
        output = vault_path / root / "briefs" / f"{timestamp_for_filename()}-{slug_for_filename(name)}-project-brief.md"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_project_brief(vault_path, root, filters, drops), encoding="utf-8")

    payload = {
        "created_at": utc_now_iso(),
        "filters": filters,
        "summary": {
            "sources": len(drops),
            "pearls": sum(1 for drop in drops if bool(drop.get("pearl", False))),
            "missing_summaries": sum(1 for drop in drops if not str(drop.get("summary") or "").strip()),
        },
        "items": drops,
    }
    return output, payload


def export_review_session(
    vault: Path,
    root: str = "MemoReef",
    output: Path | None = None,
    filters: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    filters = filters or default_review_filters()
    payload = build_review_session_payload(vault_path, root, filters)

    if output is None:
        output = vault_path / root / "review-sessions" / f"{timestamp_for_filename()}-review-session.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output, payload


def build_review_session_payload(
    vault: Path,
    root: str = "MemoReef",
    filters: dict[str, object] | None = None,
) -> dict[str, object]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    filters = filters or default_review_filters()
    drops = []
    if drops_dir.exists():
        for path in sorted(drops_dir.rglob("*.md")):
            drop = markdown_drop_to_filtered_review_item(path, vault_path)
            if review_item_matches_filters(drop, filters):
                drops.append(drop)
    drops.sort(key=lambda drop: (drop.get("status") != "drift", str(drop.get("path", ""))))
    limit = filters.get("limit")
    if isinstance(limit, int) and limit >= 0:
        drops = drops[:limit]

    drift_count = sum(1 for drop in drops if drop.get("status") == "drift")
    payload = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "filters": filters,
        "stats": {
            "total": len(drops),
            "drift": drift_count,
        },
        "items": drops,
        "drops": drops,
    }
    return payload


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


def parse_iso_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.now(timezone.utc)
    normalized = value.strip().strip('"')
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def discard_delete_after(reviewed_at: object, days: int = 30) -> str:
    return (parse_iso_datetime(reviewed_at) + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def discarded_target_for_drop(target: Path, drops_dir: Path, discarded_dir: Path) -> Path:
    relative = target.relative_to(drops_dir)
    destination = discarded_dir / relative
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    counter = 2
    while True:
        candidate = destination.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def apply_review_decisions(
    vault: Path,
    decisions: Path,
    root: str = "MemoReef",
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    payload = json.loads(decisions.expanduser().read_text(encoding="utf-8"))
    return apply_review_decision_payload(vault, payload, root, dry_run)


def apply_review_decision_payload(
    vault: Path,
    payload: dict[str, object],
    root: str = "MemoReef",
    dry_run: bool = False,
) -> tuple[int, int, list[str]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = (vault_path / root / "Drops").resolve()
    discarded_dir = (vault_path / root / "Discarded").resolve()
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
        if raw_decision == "sink":
            fields["discarded_at"] = str(reviewed_at)
            fields["delete_after"] = discard_delete_after(reviewed_at)
        if not dry_run:
            content = target.read_text(encoding="utf-8", errors="replace")
            updated_content = update_markdown_frontmatter(content, fields)
            if raw_decision == "sink":
                destination = discarded_target_for_drop(target, drops_dir, discarded_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(updated_content, encoding="utf-8")
                target.unlink()
            else:
                target.write_text(updated_content, encoding="utf-8")
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


def tokens_for_drop(drop: dict[str, object]) -> set[str]:
    values: list[str] = [
        str(drop.get("title") or ""),
        str(drop.get("summary") or ""),
    ]
    for key in ("tags", "folders"):
        items = drop.get(key, [])
        if isinstance(items, list):
            values.extend(str(item) for item in items)
    url = str(drop.get("url") or "")
    if url:
        parsed = urlsplit(url)
        values.extend([parsed.hostname or "", parsed.path])
    text = " ".join(values).lower()
    return {token for token in re.findall(r"[a-z0-9]+", text) if len(token) > 1}


def taste_tokens(examples: object) -> set[str]:
    if not isinstance(examples, list):
        return set()
    tokens: set[str] = set()
    for example in examples:
        if isinstance(example, dict):
            tokens.update(tokens_for_drop(example))
    return tokens


def build_proposal_rationale(scores: dict[str, int], proposed_status: str, proposed_pearl: bool) -> list[str]:
    rationale: list[str] = []
    if proposed_pearl:
        rationale.append("Strongest overlap is with Pearl examples.")
    elif proposed_status == "discarded":
        rationale.append("Strongest overlap is with Sink examples.")
    elif proposed_status == "reef":
        rationale.append("Shares tags, folders, title, summary, or URL terms with kept or Pearl examples.")
        rationale.append("No strong sink signal found.")
    else:
        rationale.append("No clear taste signal was found.")
    rationale.append(f"Local overlap scores: pearl={scores['pearl']}, keep={scores['keep']}, sink={scores['sink']}.")
    return rationale


def classify_proposal(drop: dict[str, object], taste_examples: dict[str, object]) -> dict[str, object]:
    drop_tokens = tokens_for_drop(drop)
    scores = {
        "pearl": len(drop_tokens & taste_tokens(taste_examples.get("pearl"))),
        "keep": len(drop_tokens & taste_tokens(taste_examples.get("keep"))),
        "sink": len(drop_tokens & taste_tokens(taste_examples.get("sink"))),
    }
    positive_score = max(scores["pearl"], scores["keep"])
    ordered_scores = sorted(scores.values(), reverse=True)
    top_score = ordered_scores[0] if ordered_scores else 0
    second_score = ordered_scores[1] if len(ordered_scores) > 1 else 0
    clearly_dominant = top_score >= 2 and top_score >= second_score + 2

    proposed_status = "drift"
    if scores["sink"] >= 2 and scores["sink"] >= positive_score + 2:
        proposed_status = "discarded"
    elif positive_score >= 2 and positive_score >= scores["sink"] + 2:
        proposed_status = "reef"

    proposed_pearl = scores["pearl"] >= 2 and scores["pearl"] >= max(scores["keep"], scores["sink"]) + 2
    if proposed_pearl:
        proposed_status = "reef"

    if clearly_dominant:
        confidence = "high"
    elif top_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    if proposed_pearl:
        priority = "high"
        note_location = "MemoReef/Pearls"
    elif proposed_status == "reef":
        priority = "normal"
        note_location = "MemoReef/Reef"
    elif proposed_status == "discarded":
        priority = "low"
        note_location = "MemoReef/Discarded"
    else:
        priority = "low"
        note_location = "MemoReef/Drops"

    tags = drop.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    return {
        "id": drop.get("id", ""),
        "path": drop.get("path", ""),
        "title": drop.get("title", ""),
        "url": drop.get("url", ""),
        "current_status": drop.get("status", "drift"),
        "proposed_status": proposed_status,
        "proposed_pearl": proposed_pearl,
        "confidence": confidence,
        "priority": priority,
        "suggested_tags": [str(tag) for tag in tags],
        "suggested_note_location": note_location,
        "rationale": build_proposal_rationale(scores, proposed_status, proposed_pearl),
        "requires_user_review": confidence != "high",
    }


def draft_agent_proposals(plan: Path, output: Path | None = None) -> tuple[Path, dict[str, object], list[str]]:
    plan_path = plan.expanduser().resolve()
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    warnings: list[str] = []

    remaining_drops = payload.get("remaining_drops")
    if not isinstance(remaining_drops, list):
        warnings.append("remaining_drops must be a list")
        remaining_drops = []

    raw_taste_examples = payload.get("taste_examples", {})
    if not isinstance(raw_taste_examples, dict):
        warnings.append("taste_examples must be an object")
        raw_taste_examples = {}

    proposals = [classify_proposal(drop, raw_taste_examples) for drop in remaining_drops if isinstance(drop, dict)]
    skipped = len(remaining_drops) - len(proposals)
    if skipped:
        warnings.append(f"skipped {skipped} malformed remaining Drops")

    if output is None:
        output = plan_path.parent / f"{timestamp_for_filename()}-agent-proposals.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "proposed": len(proposals),
        "pearl": sum(1 for proposal in proposals if proposal["proposed_pearl"]),
        "reef": sum(1 for proposal in proposals if proposal["proposed_status"] == "reef"),
        "discarded": sum(1 for proposal in proposals if proposal["proposed_status"] == "discarded"),
        "needs_review": sum(1 for proposal in proposals if proposal["requires_user_review"]),
    }
    proposal_payload = {
        "version": 1,
        "created_at": utc_now_iso(),
        "plan_source": str(plan_path),
        "summary": summary,
        "proposals": proposals,
        "warnings": warnings,
    }
    output.write_text(json.dumps(proposal_payload, indent=2) + "\n", encoding="utf-8")
    return output, proposal_payload, warnings


def apply_agent_proposals(
    vault: Path,
    proposals: Path,
    root: str = "MemoReef",
    dry_run: bool = False,
    include_needs_review: bool = False,
) -> tuple[int, int, list[str]]:
    vault_path = vault.expanduser().resolve()
    proposals_path = proposals.expanduser().resolve()
    payload = json.loads(proposals_path.read_text(encoding="utf-8"))
    proposal_items = payload.get("proposals")

    warnings: list[str] = []
    updated = 0
    skipped = 0

    if not isinstance(proposal_items, list):
        return 0, 1, ["proposals must be a list"]

    for index, item in enumerate(proposal_items, start=1):
        if not isinstance(item, dict):
            skipped += 1
            warnings.append(f"proposal {index}: malformed proposal")
            continue

        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            skipped += 1
            warnings.append(f"proposal {index}: missing path")
            continue

        if item.get("requires_user_review") is True and not include_needs_review:
            skipped += 1
            continue

        proposed_status = item.get("proposed_status")
        if proposed_status not in {"reef", "discarded", "drift"}:
            skipped += 1
            warnings.append(f"{raw_path}: unsupported proposed_status")
            continue

        proposed_pearl = item.get("proposed_pearl")
        if not isinstance(proposed_pearl, bool):
            warnings.append(f"{raw_path}: proposed_pearl must be boolean; using false")
            proposed_pearl = False

        relative_path = Path(raw_path)
        if relative_path.is_absolute():
            skipped += 1
            warnings.append(f"{raw_path}: path must be relative to the vault")
            continue

        target = (vault_path / relative_path).resolve()
        try:
            target.relative_to(vault_path)
        except ValueError:
            skipped += 1
            warnings.append(f"{raw_path}: path is outside the vault")
            continue

        if target.suffix != ".md":
            skipped += 1
            warnings.append(f"{raw_path}: not a Markdown Drop")
            continue
        if not target.exists():
            skipped += 1
            warnings.append(f"{raw_path}: file not found")
            continue

        priority = item.get("priority")
        if not isinstance(priority, str) or not priority.strip():
            priority = "normal" if proposed_status == "reef" else "low"
        note_location = item.get("suggested_note_location")
        if not isinstance(note_location, str) or not note_location.strip():
            note_location = "MemoReef/Pearls" if proposed_pearl else "MemoReef/Reef" if proposed_status == "reef" else "MemoReef/Discarded" if proposed_status == "discarded" else "MemoReef/Drops"
        confidence = item.get("confidence")
        if not isinstance(confidence, str) or not confidence.strip():
            confidence = "unknown"

        updates = {
            "status": proposed_status,
            "pearl": proposed_pearl,
            "priority": priority,
            "note_location": note_location,
            "agent_proposed_at": utc_now_iso(),
            "agent_confidence": confidence,
        }
        if not dry_run:
            content = target.read_text(encoding="utf-8", errors="replace")
            target.write_text(update_markdown_frontmatter(content, updates), encoding="utf-8")
        updated += 1

    return updated, skipped, warnings


def duplicate_drop_item(drop: dict[str, object]) -> dict[str, object]:
    return {
        "id": drop.get("id", ""),
        "path": drop.get("path", ""),
        "title": drop.get("title", ""),
        "url": drop.get("url", ""),
        "status": drop.get("status", "drift"),
        "pearl": bool(drop.get("pearl", False)),
    }


def grouped_duplicates(groups: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    result = []
    for key, drops in sorted(groups.items()):
        if len(drops) < 2:
            continue
        result.append({"key": key, "count": len(drops), "drops": [duplicate_drop_item(drop) for drop in drops]})
    return result


TITLE_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "your", "you", "are", "was", "were",
    "this", "that", "not", "but", "can", "how", "why", "what", "when", "where",
}


def title_tokens(title: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", title.lower()) if len(token) >= 3 and token not in TITLE_STOPWORDS}


def similar_title_groups(drops: list[dict[str, object]]) -> list[dict[str, object]]:
    token_sets = [title_tokens(str(drop.get("title") or "")) for drop in drops]
    parent = list(range(len(drops)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        root_a = find(a)
        root_b = find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for i, tokens_i in enumerate(token_sets):
        if len(tokens_i) < 3:
            continue
        for j in range(i + 1, len(drops)):
            tokens_j = token_sets[j]
            if len(tokens_j) < 3:
                continue
            overlap = tokens_i & tokens_j
            union_size = len(tokens_i | tokens_j)
            jaccard = len(overlap) / union_size if union_size else 0
            if len(overlap) >= 3 and jaccard >= 0.6:
                union(i, j)

    grouped: dict[int, list[dict[str, object]]] = {}
    for index, drop in enumerate(drops):
        grouped.setdefault(find(index), []).append(drop)

    result = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        key = " | ".join(sorted(str(drop.get("title") or "") for drop in group))
        result.append({"key": key, "count": len(group), "drops": [duplicate_drop_item(drop) for drop in group]})
    return sorted(result, key=lambda item: str(item["key"]))


def create_duplicate_report(vault: Path, root: str = "MemoReef", output: Path | None = None) -> tuple[Path, dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops = load_drop_items(vault_path, root)
    exact_url: dict[str, list[dict[str, object]]] = {}
    same_domain: dict[str, list[dict[str, object]]] = {}
    warnings: list[str] = []

    for drop in drops:
        raw_url = drop.get("url")
        path = drop.get("path", "unknown")
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        canonical = canonicalize_url(raw_url)
        if not canonical:
            continue
        exact_url.setdefault(canonical, []).append(drop)
        hostname = urlsplit(canonical).hostname
        if hostname:
            same_domain.setdefault(hostname.lower(), []).append(drop)
        else:
            warnings.append(f"{path}: URL has no hostname")

    groups = {
        "exact_url": grouped_duplicates(exact_url),
        "same_domain": grouped_duplicates(same_domain),
        "similar_title": similar_title_groups(drops),
    }
    affected = {
        str(drop.get("path", ""))
        for group_list in groups.values()
        for group in group_list
        for drop in group["drops"]
    }

    if output is None:
        output = vault_path / root / "reports" / f"{timestamp_for_filename()}-duplicate-report.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "summary": {
            "total_drops": len(drops),
            "exact_url_groups": len(groups["exact_url"]),
            "same_domain_groups": len(groups["same_domain"]),
            "similar_title_groups": len(groups["similar_title"]),
            "affected_drops": len(affected),
        },
        "groups": groups,
        "warnings": warnings,
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output, report


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def pilot_readme_text(vault: Path, root: str, summary: dict[str, object]) -> str:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    source_kind = str(summary.get("source_kind") or "source")
    source_path = Path(str(summary.get("source_path") or "")).expanduser()
    written_count = int(summary.get("written_count") or 0)
    review_limit = int(summary.get("review_limit") or 25)
    review_session = Path(str(summary.get("review_session") or root_path / "review-sessions"))
    duplicate_report = summary.get("duplicate_report")
    app_pilot = root_path / "app" / "pilot.html"
    app_tour = root_path / "app" / "tour.html"
    app_dashboard = root_path / "app" / "index.html"
    review_mode = repo_root() / "site" / "swipe.html"
    commands = [str(command) for command in summary.get("commands", []) if str(command).strip()]
    duplicate_line = f"- Duplicate report: `{duplicate_report}`" if duplicate_report else "- Duplicate report: skipped by `--skip-reports`."
    commands_text = "\n".join(f"- `{command}`" for command in commands) if commands else "- No command summary recorded."

    return f"""# MemoReef Pilot Checklist

## Start here

Open the generated pilot page first:

```bash
open {app_pilot}
```

Then open the product tour and dashboard:

```bash
open {app_tour}
open {app_dashboard}
```

## What was generated

- Source type: `{source_kind}`
- Source file: `{source_path.expanduser().resolve()}`
- Imported Drops: {written_count}
- Review limit: {review_limit}
- Review session JSON: `{review_session}`
{duplicate_line}
- Static app folder: `{root_path / "app"}`

## Commands already run

{commands_text}

## Review a few items

Open Review Mode:

```bash
open {review_mode}
```

Use the file picker on that page to load:

```text
{review_session}
```

Review a few Drops, then export the decisions JSON from the browser. The browser usually saves it as `memoreef-review-decisions.json`.

## Apply decisions and regenerate the app

First do a dry run:

```bash
python3 -m memoreef.cli apply-review-decisions --vault {vault_path} --root {root} --decisions /path/to/memoreef-review-decisions.json --dry-run
```

Then apply deliberately:

```bash
python3 -m memoreef.cli apply-review-decisions --vault {vault_path} --root {root} --decisions /path/to/memoreef-review-decisions.json
python3 -m memoreef.cli app --vault {vault_path} --root {root}
```

## Create a project brief after review

Use a project name from your Drops if you have one, or start broad:

```bash
python3 -m memoreef.cli brief --vault {vault_path} --root {root} --limit 10
python3 -m memoreef.cli app --vault {vault_path} --root {root}
open {root_path / "app" / "briefs.html"}
```

## Privacy note

All pilot files stay local. The pilot command imports your export, creates Markdown Drops, writes JSON reports, and generates static HTML pages inside `{root_path}`. It does not call the network, does not call AI or LLM APIs, and does not start a server.

## Feedback questions

- Did your bookmarks, links, or CSV import successfully?
- Which step was confusing or too manual?
- Did Review Mode help you find useful sources?
- Which source details were missing or hard to trust?
- What feature would make this worth using again?
- Would you use MemoReef again for a real saved-link backlog?
"""


def write_pilot_readme(vault: Path, root: str, summary: dict[str, object]) -> Path:
    vault_path = vault.expanduser().resolve()
    path = vault_path / root / "PILOT_README.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(pilot_readme_text(vault_path, root, summary), encoding="utf-8")
    return path


def run_pilot(
    vault: Path,
    root: str,
    source_kind: str,
    source_path: Path,
    allow_duplicates: bool = False,
    review_limit: int = 25,
    skip_reports: bool = False,
) -> dict[str, object]:
    if source_kind == "bookmarks":
        bookmarks = parse_bookmarks_html(source_path)
        import_command = f"python3 -m memoreef.cli import {source_path} --vault {vault} --root {root}"
    elif source_kind == "links":
        bookmarks = parse_links_text(source_path)
        import_command = f"python3 -m memoreef.cli import-links {source_path} --vault {vault} --root {root}"
    elif source_kind == "csv":
        bookmarks = parse_links_csv(source_path)
        import_command = f"python3 -m memoreef.cli import-csv {source_path} --vault {vault} --root {root}"
    else:
        raise ValueError(f"unsupported pilot source kind: {source_kind}")

    if allow_duplicates:
        import_command += " --allow-duplicates"
    written = import_bookmarks(bookmarks, source_path, vault, root, allow_duplicates)
    review_filters = default_review_filters(status=["drift"], limit=review_limit)
    review_session, review_payload = export_review_session(vault, root, None, review_filters)
    duplicate_report: Path | None = None
    duplicate_payload: dict[str, object] | None = None
    if not skip_reports:
        duplicate_report, duplicate_payload = create_duplicate_report(vault, root)
    commands = [
        import_command,
        f"python3 -m memoreef.cli export-review-session --vault {vault} --root {root} --status drift --limit {review_limit}",
    ]
    if skip_reports:
        commands.append("# duplicate-report skipped by --skip-reports")
    else:
        commands.append(f"python3 -m memoreef.cli duplicate-report --vault {vault} --root {root}")

    summary: dict[str, object] = {
        "source_kind": source_kind,
        "source_path": source_path,
        "written_count": len(written),
        "review_limit": review_limit,
        "review_session": review_session,
        "review_items": review_payload.get("stats", {}).get("total", 0) if isinstance(review_payload.get("stats"), dict) else 0,
        "duplicate_report": duplicate_report,
        "duplicate_groups": duplicate_payload.get("summary", {}).get("exact_url_groups", 0)
        if isinstance(duplicate_payload, dict) and isinstance(duplicate_payload.get("summary"), dict)
        else 0,
        "commands": commands,
        "skip_reports": skip_reports,
    }
    pilot_readme = write_pilot_readme(vault, root, summary)
    app_dashboard = generate_app_dashboard(vault, root)
    commands.append(f"python3 -m memoreef.cli app --vault {vault} --root {root}")
    summary.update(
        {
            "pilot_readme": pilot_readme,
            "app_dashboard": app_dashboard,
            "app_pilot": vault.expanduser().resolve() / root / "app" / "pilot.html",
            "app_tour": vault.expanduser().resolve() / root / "app" / "tour.html",
        }
    )
    write_pilot_readme(vault, root, summary)
    return summary


def pilot_check(vault: Path, root: str = "MemoReef") -> tuple[bool, list[str]]:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    checks = [
        ("Drops", any((root_path / "Drops").rglob("*.md")) if (root_path / "Drops").exists() else False),
        ("PILOT_README.md", (root_path / "PILOT_README.md").exists()),
        ("app/index.html", (root_path / "app" / "index.html").exists()),
        ("app/pilot.html", (root_path / "app" / "pilot.html").exists()),
        ("app/tour.html", (root_path / "app" / "tour.html").exists()),
        ("review session", any((root_path / "review-sessions").glob("*-review-session.json")) if (root_path / "review-sessions").exists() else False),
    ]
    messages = [f"{'ok' if passed else 'missing'}: {name}" for name, passed in checks]
    return all(passed for _name, passed in checks), messages


def classify_http_status(status: int | None) -> str:
    if status is None:
        return "unknown"
    if 200 <= status <= 399:
        return "ok"
    if status in {404, 410}:
        return "broken"
    if status in {401, 403, 429} or 500 <= status <= 599:
        return "suspicious"
    return "unknown"


def request_link(url: str, method: str, timeout: float) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        method=method.upper(),
        headers={"User-Agent": "MemoReef/0.1 local link checker"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if method.lower() == "get":
                response.read(1024)
            status = int(response.getcode())
            return {
                "status": classify_http_status(status),
                "http_status": status,
                "method": method.upper(),
                "final_url": response.geturl(),
                "error": None,
            }
    except urllib.error.HTTPError as error:
        status = int(error.code)
        return {
            "status": classify_http_status(status),
            "http_status": status,
            "method": method.upper(),
            "final_url": error.geturl(),
            "error": None,
        }
    except (TimeoutError, urllib.error.URLError, OSError) as error:
        return {
            "status": "unknown",
            "http_status": None,
            "method": method.upper(),
            "final_url": url,
            "error": str(error),
        }


def should_fallback_to_get(result: dict[str, object]) -> bool:
    return result.get("status") == "unknown" or result.get("http_status") in {403, 405}


def check_link(url: str, timeout: float, method: str) -> dict[str, object]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return {
            "status": "unknown",
            "http_status": None,
            "method": None,
            "final_url": url,
            "error": "unsupported URL scheme",
        }
    if not parsed.netloc:
        return {
            "status": "unknown",
            "http_status": None,
            "method": None,
            "final_url": url,
            "error": "malformed URL",
        }

    if method == "get":
        return request_link(url, "GET", timeout)
    if method == "head":
        return request_link(url, "HEAD", timeout)

    head_result = request_link(url, "HEAD", timeout)
    if should_fallback_to_get(head_result):
        return request_link(url, "GET", timeout)
    return head_result


def create_link_check_report(
    vault: Path,
    root: str = "MemoReef",
    output: Path | None = None,
    timeout: float = 5,
    limit: int | None = None,
    method: str = "auto",
) -> tuple[Path, dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops = load_drop_items(vault_path, root)
    if limit is not None:
        drops = drops[: max(0, limit)]

    warnings: list[str] = []
    results: list[dict[str, object]] = []
    skipped = 0

    for drop in drops:
        raw_url = drop.get("url")
        path = str(drop.get("path", "unknown"))
        if not isinstance(raw_url, str) or not raw_url.strip():
            skipped += 1
            warnings.append(f"{path}: missing URL")
            continue

        result = check_link(raw_url.strip(), timeout, method)
        results.append(
            {
                "id": drop.get("id", ""),
                "path": path,
                "title": drop.get("title", ""),
                "url": raw_url.strip(),
                "status": result["status"],
                "http_status": result["http_status"],
                "method": result["method"],
                "final_url": result["final_url"],
                "error": result["error"],
            }
        )

    summary = {
        "total_drops": len(drops),
        "checked": len(results),
        "ok": sum(1 for item in results if item["status"] == "ok"),
        "broken": sum(1 for item in results if item["status"] == "broken"),
        "suspicious": sum(1 for item in results if item["status"] == "suspicious"),
        "unknown": sum(1 for item in results if item["status"] == "unknown"),
        "skipped": skipped,
    }

    if output is None:
        output = vault_path / root / "reports" / f"{timestamp_for_filename()}-link-check-report.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "summary": summary,
        "results": results,
        "warnings": warnings,
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output, report


class PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.description: str | None = None
        self.og_title: str | None = None
        self.og_description: str | None = None
        self.canonical_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
        if tag == "title":
            self.in_title = True
            return
        if tag == "meta":
            name = attrs_dict.get("name", "").lower()
            property_name = attrs_dict.get("property", "").lower()
            content = clean_metadata_text(attrs_dict.get("content", ""))
            if not content:
                return
            if name == "description" and self.description is None:
                self.description = content
            elif property_name == "og:title" and self.og_title is None:
                self.og_title = content
            elif property_name == "og:description" and self.og_description is None:
                self.og_description = content
            return
        if tag == "link":
            rel_values = {value.lower() for value in attrs_dict.get("rel", "").split()}
            href = attrs_dict.get("href", "").strip()
            if "canonical" in rel_values and href and self.canonical_url is None:
                self.canonical_url = href

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    def metadata(self) -> dict[str, str]:
        return {
            "title": clean_metadata_text("".join(self.title_parts)),
            "description": self.description or "",
            "og_title": self.og_title or "",
            "og_description": self.og_description or "",
            "canonical_url": self.canonical_url or "",
        }


def clean_metadata_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def response_charset(response: object) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    get_content_charset = getattr(headers, "get_content_charset", None)
    if callable(get_content_charset):
        return get_content_charset()
    return None


def fetch_page_metadata(url: str, timeout: float) -> dict[str, object]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return {"status": "unknown", "error": "unsupported URL scheme"}
    if not parsed.netloc:
        return {"status": "unknown", "error": "malformed URL"}

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "MemoReef/0.1 local metadata refresh"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(256 * 1024)
            final_url = response.geturl() or url
            charset = response_charset(response) or "utf-8"
            html = data.decode(charset, errors="replace")
    except urllib.error.HTTPError as error:
        return {"status": "unknown", "error": f"HTTP {error.code}"}
    except Exception as error:
        return {"status": "unknown", "error": str(error)}

    parser = PageMetadataParser()
    try:
        parser.feed(html)
    except Exception as error:
        return {"status": "unknown", "error": f"metadata parse failed: {error}"}

    metadata = parser.metadata()
    canonical_url = ""
    if metadata["canonical_url"]:
        canonical_url = canonicalize_url(urljoin(final_url, metadata["canonical_url"]))

    hostname = urlsplit(final_url or url).hostname or urlsplit(url).hostname or ""
    return {
        "status": "ok",
        "error": "",
        "page_title": metadata["og_title"] or metadata["title"],
        "page_description": metadata["og_description"] or metadata["description"],
        "canonical_url": canonical_url,
        "hostname": hostname.lower(),
    }


def refresh_metadata(
    vault: Path,
    root: str = "MemoReef",
    dry_run: bool = False,
    limit: int | None = None,
    timeout: float = 5,
) -> tuple[int, int, list[str], list[str]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    drop_paths = sorted(drops_dir.rglob("*.md")) if drops_dir.exists() else []
    if limit is not None:
        drop_paths = drop_paths[: max(0, limit)]

    updated = 0
    skipped = 0
    warnings: list[str] = []
    planned: list[str] = []

    for path in drop_paths:
        drop = markdown_drop_to_review_item(path, vault_path)
        raw_url = drop.get("url")
        relative_path = str(drop.get("path", path.name))
        if not isinstance(raw_url, str) or not raw_url.strip():
            skipped += 1
            warnings.append(f"{relative_path}: missing URL")
            continue

        refreshed_at = utc_now_iso()
        metadata = fetch_page_metadata(raw_url.strip(), timeout)
        status = str(metadata.get("status") or "unknown")
        error = str(metadata.get("error") or "")
        if status != "ok" and error:
            warnings.append(f"{relative_path}: {error}")

        updates = {
            "page_title": str(metadata.get("page_title") or ""),
            "page_description": str(metadata.get("page_description") or ""),
            "canonical_url": str(metadata.get("canonical_url") or ""),
            "hostname": str(metadata.get("hostname") or ""),
            "metadata_refreshed_at": refreshed_at,
            "metadata_status": status,
            "metadata_error": error,
        }
        planned.append(relative_path)
        if not dry_run:
            content = path.read_text(encoding="utf-8", errors="replace")
            path.write_text(update_markdown_frontmatter(content, updates), encoding="utf-8")
        updated += 1

    return updated, skipped, warnings, planned


GARDEN_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "your", "you", "are", "was", "were",
    "this", "that", "not", "but", "can", "how", "why", "what", "when", "where",
    "about", "guide", "article", "page", "local",
}

TAG_STOPWORDS = GARDEN_STOPWORDS | {
    "com", "www", "http", "https", "html", "blog", "news", "post", "posts", "read", "reading",
    "best", "new", "free", "review", "reviews", "source", "sources", "bookmark", "bookmarks",
    "memo", "memoreef", "drop", "drops", "untitled", "not", "enriched", "yet", "example",
}


def tag_slug(value: str, max_len: int = 42) -> str:
    value = value.lower().strip()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:max_len].strip("-")


def tag_tokens_from_text(value: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        token = singularize_token(token)
        if len(token) >= 3 and token not in TAG_STOPWORDS:
            tokens.append(token)
    return tokens


def reviewed_drop_for_tagging(frontmatter: dict[str, object]) -> bool:
    status = str(frontmatter.get("status") or "").strip().lower()
    return bool(frontmatter.get("pearl", False)) or status in {"reef", "deep"}


def tag_candidate_scores(frontmatter: dict[str, object], body: str) -> dict[str, int]:
    scores: dict[str, int] = {}

    def add(tag: str, weight: int = 1) -> None:
        normalized = tag_slug(tag)
        if not normalized or normalized in TAG_STOPWORDS or len(normalized) < 3:
            return
        scores[normalized] = scores.get(normalized, 0) + weight

    for key in ("tags", "folders", "projects", "shoals"):
        for label in garden_list(frontmatter.get(key)):
            add(label, 4 if key == "tags" else 3)

    hostname = str(frontmatter.get("hostname") or "") or (urlsplit(str(frontmatter.get("canonical_url") or frontmatter.get("url") or "")).hostname or "")
    for host_part in hostname.lower().split("."):
        add(host_part, 1)

    text_fields = [
        str(frontmatter.get("title") or ""),
        str(frontmatter.get("page_title") or ""),
        str(frontmatter.get("page_description") or ""),
        str(frontmatter.get("url") or ""),
        body,
    ]
    for key in ("title", "page_title"):
        for token in tag_tokens_from_text(str(frontmatter.get(key) or "")):
            add(token, 3)
    token_stream = tag_tokens_from_text(" ".join(text_fields))
    for token in token_stream:
        add(token, 1)
    for left, right in zip(token_stream, token_stream[1:]):
        if left != right:
            add(f"{left}-{right}", 2)

    return scores


def suggested_tags_for_drop(frontmatter: dict[str, object], body: str, max_tags: int = 6) -> list[str]:
    existing = {tag_slug(tag) for tag in garden_list(frontmatter.get("tags"))}
    scored = tag_candidate_scores(frontmatter, body)
    ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))
    suggestions: list[str] = []
    for tag, _score in ranked:
        if tag in existing or tag in suggestions:
            continue
        suggestions.append(tag)
        if len(suggestions) >= max_tags:
            break
    return suggestions


def tag_reviewed_drops(vault: Path, root: str = "MemoReef", dry_run: bool = False, limit: int | None = None) -> dict[str, object]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    warnings: list[str] = []
    items: list[dict[str, object]] = []
    considered = 0
    eligible = 0
    updated = 0
    tags_added = 0

    if not drops_dir.exists():
        return {
            "ok": True,
            "considered": 0,
            "eligible": 0,
            "updated": 0,
            "tags_added": 0,
            "items": [],
            "warnings": [f"{root}/Drops not found"],
        }

    for path in sorted(drops_dir.rglob("*.md")):
        if limit is not None and considered >= limit:
            break
        considered += 1
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            frontmatter, body = parse_markdown_frontmatter(content)
        except OSError as error:
            warnings.append(f"{path}: {error}")
            continue
        if not reviewed_drop_for_tagging(frontmatter):
            continue
        eligible += 1
        existing_tags = existing_frontmatter_labels(frontmatter.get("tags"))
        suggestions = suggested_tags_for_drop(frontmatter, body)
        updated_tags, added_count = append_unique_labels(existing_tags, suggestions)
        relative_path = path.resolve().relative_to(vault_path).as_posix()
        items.append(
            {
                "path": relative_path,
                "title": str(frontmatter.get("title") or path.stem),
                "added_tags": suggestions,
                "existing_tags": existing_tags,
            }
        )
        if added_count == 0:
            continue
        if not dry_run:
            updates = {
                "tags": updated_tags,
                "agent_tagged_at": utc_now_iso(),
                "agent_tag_count": len(updated_tags),
            }
            path.write_text(update_markdown_frontmatter(content, updates), encoding="utf-8")
        updated += 1
        tags_added += added_count

    return {
        "ok": True,
        "considered": considered,
        "eligible": eligible,
        "updated": updated,
        "tags_added": tags_added,
        "items": items,
        "warnings": warnings,
    }


HUB_CONNECTIONS_START = "<!-- memoreef-connections:start -->"
HUB_CONNECTIONS_END = "<!-- memoreef-connections:end -->"

HUB_NOISE_LABELS = TAG_STOPWORDS | {
    "all", "archive", "article", "articles", "bar", "bookmark-bar", "bookmarks-bar",
    "browser", "click", "collection", "default", "folder", "folders", "home", "inbox",
    "item", "items", "later", "link", "links", "misc", "mobile", "newsletter", "old",
    "other", "personal", "private", "saved", "stuff", "tab", "tabs", "todo", "uncategorized",
    "unfiled", "unsorted", "utm", "utm-campaign", "utm-content", "utm-medium", "utm-source",
    "work", "www",
    # Common browser/bookmark-folder sediment from real imports.
    "lesezeichenleiste", "bookmarks", "bookmark", "bookmarks-menu", "favorites", "favourites",
    "neuer-ordner", "new-folder", "zuvieletabsoffen", "too-many-tabs-open",
    # Workflow/action labels are useful metadata, but bad graph hubs.
    "action", "action-triage", "agent-brief", "brief", "brief-status", "drift-suggested",
    "docs-google", "google", "google-docs", "google-drive", "drive-google",
    "create", "generator", "generators", "tool", "tools", "youtube-watch",
}

HOST_NOISE_PARTS = {
    "app", "blog", "cdn", "co", "com", "dev", "docs", "edu", "gov", "io", "net", "news",
    "org", "uk", "www",
}


def strip_generated_hub_connections(content: str) -> str:
    pattern = re.compile(
        rf"\n*{re.escape(HUB_CONNECTIONS_START)}.*?{re.escape(HUB_CONNECTIONS_END)}\n*",
        re.DOTALL,
    )
    return pattern.sub("\n", content).rstrip() + "\n"


def hub_label_slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")


def hub_label_from_raw(value: str) -> str:
    acronyms = {"ai", "ar", "vr", "xr", "ui", "ux", "api", "llm"}
    words = []
    for part in re.split(r"[^A-Za-z0-9]+", value.strip()):
        if not part:
            continue
        if part.casefold() in acronyms:
            words.append(part.upper())
        elif part.isupper() and len(part) <= 4:
            words.append(part)
        else:
            words.append(part.capitalize())
    return " ".join(words).strip()


def hub_label_is_noise(label: str) -> bool:
    slug = hub_label_slug(label)
    compact = slug.replace("-", "")
    if not slug or len(compact) < 3:
        return True
    if compact.isdigit() or re.fullmatch(r"\d{2,}", compact):
        return True
    if slug in HUB_NOISE_LABELS or compact in HUB_NOISE_LABELS:
        return True
    if slug.startswith("utm-"):
        return True
    parts = [part for part in slug.split("-") if part]
    if parts and all(part in HUB_NOISE_LABELS or part in HOST_NOISE_PARTS for part in parts):
        return True
    return False


def add_hub_label(scores: dict[str, dict[str, object]], raw_label: str, drop: dict[str, object], weight: int) -> None:
    label = hub_label_from_raw(raw_label)
    if hub_label_is_noise(label):
        return
    slug = hub_label_slug(label)
    bucket = scores.setdefault(slug, {"label": label, "score": 0, "drops": {}})
    bucket["score"] = int(bucket["score"]) + weight
    drops = bucket["drops"]
    if isinstance(drops, dict):
        drops[str(drop.get("path") or "")] = drop


def add_hub_tokens(scores: dict[str, dict[str, object]], text: str, drop: dict[str, object], weight: int) -> None:
    for token in tag_tokens_from_text(text):
        label = hub_label_from_raw(token)
        add_hub_label(scores, label, drop, weight)


def reviewed_hub_drop(frontmatter: dict[str, object]) -> bool:
    return reviewed_drop_for_tagging(frontmatter)


def hub_drop_item(path: Path, vault: Path) -> dict[str, object]:
    relative_path = path.resolve().relative_to(vault.resolve()).as_posix()
    content = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = parse_markdown_frontmatter(content)
    url = str(frontmatter.get("url") or "")
    canonical = str(frontmatter.get("canonical_url") or "")
    hostname = str(frontmatter.get("hostname") or "") or (urlsplit(canonical or url).hostname or "")
    return {
        "path": relative_path,
        "file": path,
        "title": str(frontmatter.get("title") or path.stem),
        "url": url,
        "status": str(frontmatter.get("status") or "drift"),
        "pearl": bool(frontmatter.get("pearl", False)),
        "tags": garden_list(frontmatter.get("tags")),
        "projects": garden_list(frontmatter.get("projects")),
        "shoals": garden_list(frontmatter.get("shoals")),
        "hostname": hostname.lower(),
        "page_title": str(frontmatter.get("page_title") or ""),
        "page_description": str(frontmatter.get("page_description") or ""),
        "metadata_refreshed_at": str(frontmatter.get("metadata_refreshed_at") or ""),
        "frontmatter": frontmatter,
        "body": body,
    }


def load_reviewed_hub_drops(vault: Path, root: str = "MemoReef") -> list[dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    if not drops_dir.exists():
        return []
    drops: list[dict[str, object]] = []
    for path in sorted(drops_dir.rglob("*.md")):
        content = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, _body = parse_markdown_frontmatter(content)
        if reviewed_hub_drop(frontmatter):
            drops.append(hub_drop_item(path, vault_path))
    return drops


def hub_scores_for_drops(drops: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    scores: dict[str, dict[str, object]] = {}
    for drop in drops:
        for label in garden_list(drop.get("projects")):
            add_hub_label(scores, label, drop, 6)
        for label in garden_list(drop.get("shoals")):
            add_hub_label(scores, label, drop, 5)
        for label in garden_list(drop.get("tags")):
            add_hub_label(scores, label, drop, 4)

        hostname = str(drop.get("hostname") or "")
        for part in hostname.split("."):
            if part and part not in HOST_NOISE_PARTS:
                add_hub_label(scores, part, drop, 1)

        if str(drop.get("metadata_refreshed_at") or "") or str(drop.get("page_title") or drop.get("page_description") or ""):
            add_hub_tokens(scores, str(drop.get("page_title") or ""), drop, 2)
            add_hub_tokens(scores, str(drop.get("page_description") or ""), drop, 1)
    return scores


def selected_hubs(drops: list[dict[str, object]], min_drops: int, max_hubs: int) -> list[dict[str, object]]:
    scores = hub_scores_for_drops(drops)
    hubs: list[dict[str, object]] = []
    for data in scores.values():
        raw_drops = data.get("drops", {})
        if not isinstance(raw_drops, dict):
            continue
        hub_drops = sorted(raw_drops.values(), key=lambda drop: str(drop.get("path") or ""))
        if len(hub_drops) < min_drops:
            continue
        label = str(data.get("label") or "")
        hubs.append(
            {
                "label": label,
                "slug": hub_label_slug(label),
                "score": int(data.get("score") or 0),
                "drops": hub_drops,
            }
        )
    return sorted(hubs, key=lambda hub: (-len(hub["drops"]), -int(hub["score"]), str(hub["label"])))[:max_hubs]


def obsidian_note_target(path: Path, vault: Path) -> str:
    relative = path.resolve().relative_to(vault.resolve()).with_suffix("").as_posix()
    return relative


def obsidian_link(path: Path, vault: Path, alias: str) -> str:
    return f"[[{obsidian_note_target(path, vault)}|{alias}]]"


def hub_note_path(output_dir: Path, label: str) -> Path:
    safe_name = re.sub(r"[\\\\/:*?\"<>|]+", "-", label).strip() or "Untitled"
    return output_dir / f"Hub - {safe_name}.md"


def render_hub_index(vault: Path, root: str, output_dir: Path, hubs: list[dict[str, object]]) -> str:
    lines = [
        "# Emerging Hubs",
        "",
        "<!-- memoreef-hub-map:generated -->",
        "",
        f"- Source: `{root}/Drops`",
        f"- Hubs: {len(hubs)}",
        "",
        "## Hubs",
        "",
    ]
    if not hubs:
        lines.append("No hubs met the current threshold.")
    for hub in hubs:
        label = str(hub["label"])
        note = hub_note_path(output_dir, label)
        lines.append(f"- {obsidian_link(note, vault, label)} ({len(hub['drops'])} Drops)")
    return "\n".join(lines).rstrip() + "\n"


def render_hub_note(vault: Path, root: str, label: str, drops: list[dict[str, object]]) -> str:
    lines = [
        f"# Hub - {label}",
        "",
        "<!-- memoreef-hub:generated -->",
        "",
        f"- Source: `{root}/Drops`",
        f"- Drop count: {len(drops)}",
        "",
        "## Linked Drops",
        "",
    ]
    for drop in drops:
        path = vault / str(drop.get("path") or "")
        title = str(drop.get("title") or path.stem)
        lines.append(f"- {obsidian_link(path, vault, title)}")
    return "\n".join(lines).rstrip() + "\n"


def hub_connections_section(vault: Path, output_dir: Path, hubs: list[dict[str, object]]) -> str:
    links = []
    for hub in hubs:
        label = str(hub["label"])
        links.append(obsidian_link(hub_note_path(output_dir, label), vault, label))
    return "\n".join(
        [
            HUB_CONNECTIONS_START,
            "## MemoReef Connections",
            "",
            f"- Hubs: {', '.join(links)}",
            "",
            HUB_CONNECTIONS_END,
            "",
        ]
    )


def update_drop_hub_connections(content: str, vault: Path, output_dir: Path, hubs: list[dict[str, object]]) -> str:
    base = strip_generated_hub_connections(content)
    if not hubs:
        return base
    return base.rstrip() + "\n\n" + hub_connections_section(vault, output_dir, hubs)


def create_hub_map(
    vault: Path,
    root: str = "MemoReef",
    dry_run: bool = False,
    min_drops: int = 2,
    max_hubs: int = 100,
    output_dir: Path | None = None,
) -> dict[str, object]:
    vault_path = vault.expanduser().resolve()
    min_drops = max(1, min_drops)
    max_hubs = max(1, max_hubs)
    if output_dir is None:
        maps_dir = vault_path / root / "Maps"
    elif output_dir.is_absolute():
        maps_dir = output_dir.expanduser().resolve()
    else:
        maps_dir = (vault_path / output_dir).expanduser().resolve()
    try:
        maps_dir.relative_to(vault_path)
    except ValueError as error:
        raise ValueError("--output-dir must be inside the vault so Obsidian links stay vault-relative") from error
    drops = load_reviewed_hub_drops(vault_path, root)
    hubs = selected_hubs(drops, min_drops, max_hubs)
    hubs_by_drop: dict[str, list[dict[str, object]]] = {}
    for hub in hubs:
        for drop in hub["drops"]:
            hubs_by_drop.setdefault(str(drop.get("path") or ""), []).append(hub)
    for drop_hubs in hubs_by_drop.values():
        drop_hubs.sort(key=lambda hub: str(hub["label"]))

    planned_files: list[str] = []
    changed_files: list[Path] = []
    index_path = maps_dir / "Emerging Hubs.md"
    index_text = render_hub_index(vault_path, root, maps_dir, hubs)
    if not index_path.exists() or index_path.read_text(encoding="utf-8", errors="replace") != index_text:
        planned_files.append(str(index_path))
        changed_files.append(index_path)

    hub_notes: list[Path] = []
    for hub in hubs:
        label = str(hub["label"])
        note_path = hub_note_path(maps_dir, label)
        hub_notes.append(note_path)
        note_text = render_hub_note(vault_path, root, label, hub["drops"])
        if not note_path.exists() or note_path.read_text(encoding="utf-8", errors="replace") != note_text:
            planned_files.append(str(note_path))
            changed_files.append(note_path)

    drop_updates: list[str] = []
    for drop in drops:
        file_path = drop.get("file")
        if not isinstance(file_path, Path):
            continue
        content = file_path.read_text(encoding="utf-8", errors="replace")
        updated = update_drop_hub_connections(content, vault_path, maps_dir, hubs_by_drop.get(str(drop.get("path") or ""), []))
        if updated != content:
            drop_updates.append(str(drop.get("path") or ""))
            planned_files.append(str(file_path))
            changed_files.append(file_path)

    if not dry_run:
        maps_dir.mkdir(parents=True, exist_ok=True)
        index_path.write_text(index_text, encoding="utf-8")
        for hub in hubs:
            label = str(hub["label"])
            hub_note_path(maps_dir, label).write_text(render_hub_note(vault_path, root, label, hub["drops"]), encoding="utf-8")
        for drop in drops:
            file_path = drop.get("file")
            if not isinstance(file_path, Path):
                continue
            content = file_path.read_text(encoding="utf-8", errors="replace")
            updated = update_drop_hub_connections(content, vault_path, maps_dir, hubs_by_drop.get(str(drop.get("path") or ""), []))
            if updated != content:
                file_path.write_text(updated, encoding="utf-8")

    return {
        "vault": vault_path,
        "output_dir": maps_dir,
        "index": index_path,
        "reviewed_drops": len(drops),
        "hubs": hubs,
        "hub_notes": hub_notes,
        "drop_updates": drop_updates,
        "files_that_would_change": planned_files,
        "changed_files": changed_files,
    }


def garden_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip() and str(item).strip() != "[]"]


def garden_drop_item(path: Path, vault: Path) -> dict[str, object]:
    relative_path = path.resolve().relative_to(vault.resolve()).as_posix()
    frontmatter, _body = parse_markdown_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    url = str(frontmatter.get("url") or "")
    canonical = str(frontmatter.get("canonical_url") or "")
    hostname = str(frontmatter.get("hostname") or "")
    if not hostname:
        hostname = urlsplit(canonical or url).hostname or ""

    return {
        "id": relative_path,
        "path": relative_path,
        "title": str(frontmatter.get("title") or path.stem),
        "url": url,
        "folders": garden_list(frontmatter.get("folders")),
        "tags": garden_list(frontmatter.get("tags")),
        "projects": garden_list(frontmatter.get("projects")),
        "shoals": garden_list(frontmatter.get("shoals")),
        "status": str(frontmatter.get("status") or "drift"),
        "pearl": bool(frontmatter.get("pearl", False)),
        "page_title": str(frontmatter.get("page_title") or ""),
        "page_description": str(frontmatter.get("page_description") or ""),
        "hostname": hostname.lower(),
        "canonical_url": canonical,
        "metadata_refreshed_at": str(frontmatter.get("metadata_refreshed_at") or ""),
    }


def load_garden_drop_items(vault: Path, root: str = "MemoReef") -> list[dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    if not drops_dir.exists():
        return []
    return [garden_drop_item(path, vault_path) for path in sorted(drops_dir.rglob("*.md"))]


def singularize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def garden_tokens(drop: dict[str, object]) -> set[str]:
    values = [
        str(drop.get("title") or ""),
        str(drop.get("page_title") or ""),
        str(drop.get("page_description") or ""),
        str(drop.get("hostname") or ""),
        str(urlsplit(str(drop.get("url") or "")).hostname or ""),
    ]
    for key in ("folders", "tags"):
        items = drop.get(key, [])
        if isinstance(items, list):
            values.extend(str(item) for item in items)

    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", " ".join(values).lower()):
        token = singularize_token(token)
        if len(token) >= 3 and token not in GARDEN_STOPWORDS:
            tokens.add(token)
    return tokens


def garden_example_score(candidate: dict[str, object], example: dict[str, object]) -> tuple[int, list[str]]:
    candidate_tokens = garden_tokens(candidate)
    example_tokens = garden_tokens(example)
    overlap = sorted(candidate_tokens & example_tokens)
    score = len(overlap)

    candidate_hostname = str(candidate.get("hostname") or "")
    example_hostname = str(example.get("hostname") or "")
    if candidate_hostname and candidate_hostname == example_hostname:
        score += 3

    candidate_folders = set(garden_list(candidate.get("folders")))
    example_folders = set(garden_list(example.get("folders")))
    score += 2 * len(candidate_folders & example_folders)

    candidate_tags = set(garden_list(candidate.get("tags")))
    example_tags = set(garden_list(example.get("tags")))
    score += 2 * len(candidate_tags & example_tags)

    if bool(example.get("pearl", False)):
        score += 1
    if str(example.get("status") or "") == "reef":
        score += 1
    return score, overlap


def garden_source_example(example: dict[str, object], score: int) -> dict[str, object]:
    return {
        "id": example.get("id", ""),
        "path": example.get("path", ""),
        "title": example.get("title", ""),
        "score": score,
    }


def garden_label_suggestions(
    candidate: dict[str, object],
    examples: list[dict[str, object]],
    label_key: str,
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for example in examples:
        labels = garden_list(example.get(label_key))
        if not labels:
            continue
        score, overlap = garden_example_score(candidate, example)
        if score <= 0:
            continue
        for label in labels:
            bucket = grouped.setdefault(label, {"score": 0, "evidence_tokens": set(), "source_examples": []})
            bucket["score"] = int(bucket["score"]) + score
            evidence = bucket["evidence_tokens"]
            if isinstance(evidence, set):
                evidence.update(overlap)
            source_examples = bucket["source_examples"]
            if isinstance(source_examples, list):
                source_examples.append(garden_source_example(example, score))

    suggestions = []
    for name, data in grouped.items():
        score = int(data["score"])
        if score < 2:
            continue
        source_examples = data["source_examples"]
        if not isinstance(source_examples, list):
            source_examples = []
        source_examples = sorted(
            source_examples,
            key=lambda item: (-int(item.get("score", 0)), str(item.get("title", "")), str(item.get("path", ""))),
        )[:3]
        evidence_tokens = data["evidence_tokens"]
        if not isinstance(evidence_tokens, set):
            evidence_tokens = set()
        suggestions.append(
            {
                "name": name,
                "score": score,
                "evidence_tokens": sorted(evidence_tokens),
                "source_examples": source_examples,
            }
        )
    return sorted(suggestions, key=lambda item: (-int(item["score"]), str(item["name"])))[:3]


def create_garden_suggestions_report(
    vault: Path,
    root: str = "MemoReef",
    output: Path | None = None,
) -> tuple[Path, dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops = load_garden_drop_items(vault_path, root)
    examples = [drop for drop in drops if garden_list(drop.get("projects")) or garden_list(drop.get("shoals"))]
    candidates = [
        drop
        for drop in drops
        if not garden_list(drop.get("projects")) or not garden_list(drop.get("shoals"))
    ]
    warnings: list[str] = []
    suggestions: list[dict[str, object]] = []

    if not examples:
        warnings.append("No Drops with projects or shoals found; add examples first.")
    else:
        for candidate in candidates:
            has_projects = bool(garden_list(candidate.get("projects")))
            has_shoals = bool(garden_list(candidate.get("shoals")))
            if has_projects and has_shoals:
                continue
            suggested_projects = [] if has_projects else garden_label_suggestions(candidate, examples, "projects")
            suggested_shoals = [] if has_shoals else garden_label_suggestions(candidate, examples, "shoals")
            if not suggested_projects and not suggested_shoals:
                continue
            suggestions.append(
                {
                    "id": candidate.get("id", ""),
                    "path": candidate.get("path", ""),
                    "title": candidate.get("title", ""),
                    "url": candidate.get("url", ""),
                    "suggested_projects": suggested_projects,
                    "suggested_shoals": suggested_shoals,
                }
            )

    suggestions.sort(key=lambda item: str(item.get("path", "")))

    if output is None:
        output = vault_path / root / "reports" / f"{timestamp_for_filename()}-garden-suggestions.json"
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "version": 1,
        "created_at": utc_now_iso(),
        "vault": str(vault_path),
        "source": f"{root}/Drops",
        "summary": {
            "total_drops": len(drops),
            "example_drops": len(examples),
            "candidate_drops": len(candidates),
            "suggestions": len(suggestions),
            "warnings": len(warnings),
        },
        "suggestions": suggestions,
        "warnings": warnings,
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output, report


def suggestion_label_names(item: object) -> list[str]:
    if not isinstance(item, list):
        return []
    names: list[str] = []
    for suggestion in item:
        if not isinstance(suggestion, dict):
            continue
        name = suggestion.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name)
    return names


def existing_frontmatter_labels(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip() and str(item).strip() != "[]"]


def append_unique_labels(existing: list[str], accepted: list[str]) -> tuple[list[str], int]:
    updated = list(existing)
    added = 0
    for label in accepted:
        if label not in updated:
            updated.append(label)
            added += 1
    return updated, added


def apply_garden_suggestions(
    vault: Path,
    suggestions: Path,
    root: str = "MemoReef",
    accept_all: bool = False,
    accept_projects: list[str] | None = None,
    accept_shoals: list[str] | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int, int, list[str]]:
    vault_path = vault.expanduser().resolve()
    payload = json.loads(suggestions.expanduser().read_text(encoding="utf-8"))
    suggestion_items = payload.get("suggestions")
    accepted_projects = accept_projects or []
    accepted_shoals = accept_shoals or []

    warnings: list[str] = []
    files_considered = 0
    files_updated = 0
    projects_added = 0
    shoals_added = 0

    if not isinstance(suggestion_items, list):
        return 0, 0, 0, 0, ["suggestions must be a list"]

    report_projects = {
        name
        for item in suggestion_items
        if isinstance(item, dict)
        for name in suggestion_label_names(item.get("suggested_projects"))
    }
    report_shoals = {
        name
        for item in suggestion_items
        if isinstance(item, dict)
        for name in suggestion_label_names(item.get("suggested_shoals"))
    }
    if not accept_all:
        for name in accepted_projects:
            if name not in report_projects:
                warnings.append(f'project "{name}" not present in suggestions report')
        for name in accepted_shoals:
            if name not in report_shoals:
                warnings.append(f'shoal "{name}" not present in suggestions report')

    for index, item in enumerate(suggestion_items, start=1):
        files_considered += 1
        if not isinstance(item, dict):
            warnings.append(f"suggestion {index}: malformed suggestion")
            continue

        raw_path = item.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            warnings.append(f"suggestion {index}: missing path")
            continue

        relative_path = Path(raw_path)
        if relative_path.is_absolute():
            warnings.append(f"{raw_path}: path must be relative to the vault")
            continue

        target = (vault_path / relative_path).resolve()
        try:
            target.relative_to(vault_path)
        except ValueError:
            warnings.append(f"{raw_path}: path is outside the vault")
            continue

        if target.suffix != ".md":
            warnings.append(f"{raw_path}: not a Markdown Drop")
            continue
        if not target.exists():
            warnings.append(f"{raw_path}: file not found")
            continue

        project_names = suggestion_label_names(item.get("suggested_projects"))
        shoal_names = suggestion_label_names(item.get("suggested_shoals"))
        project_accepts = project_names if accept_all else [name for name in project_names if name in accepted_projects]
        shoal_accepts = shoal_names if accept_all else [name for name in shoal_names if name in accepted_shoals]

        content = target.read_text(encoding="utf-8", errors="replace")
        frontmatter, _body = parse_markdown_frontmatter(content)
        existing_projects = existing_frontmatter_labels(frontmatter.get("projects"))
        existing_shoals = existing_frontmatter_labels(frontmatter.get("shoals"))
        updated_projects, project_count = append_unique_labels(existing_projects, project_accepts)
        updated_shoals, shoal_count = append_unique_labels(existing_shoals, shoal_accepts)

        if project_count == 0 and shoal_count == 0:
            continue

        updates: dict[str, object] = {}
        if project_count:
            updates["projects"] = updated_projects
        if shoal_count:
            updates["shoals"] = updated_shoals
        if not dry_run:
            target.write_text(update_markdown_frontmatter(content, updates), encoding="utf-8")
        files_updated += 1
        projects_added += project_count
        shoals_added += shoal_count

    return files_considered, files_updated, projects_added, shoals_added, warnings


def vault_has_metadata(vault: Path, root: str = "MemoReef") -> bool:
    return any(str(drop.get("metadata_refreshed_at") or drop.get("page_title") or "") for drop in load_garden_drop_items(vault, root))


def latest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def latest_matching_file(base: Path, patterns: list[str]) -> Path | None:
    matches: list[Path] = []
    if base.exists():
        for pattern in patterns:
            matches.extend(path for path in base.rglob(pattern) if path.is_file())
    return latest_file(matches)


def relative_or_none(path: object, base: Path) -> str:
    if not isinstance(path, Path):
        return "Not found yet"
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def dashboard_state(vault: Path, root: str = "MemoReef") -> dict[str, object]:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    drops = load_drop_items(vault_path, root)
    total = len(drops)
    drift = sum(1 for drop in drops if drop.get("status") == "drift")
    reef = sum(1 for drop in drops if drop.get("status") == "reef")
    discarded = sum(1 for drop in drops if drop.get("status") == "discarded")
    pearls = sum(1 for drop in drops if bool(drop.get("pearl", False)))

    latest_review_session = latest_matching_file(root_path / "review-sessions", ["*-review-session.json"])
    latest_review_decisions = latest_matching_file(vault_path, ["*review-decisions*.json"])
    latest_agent_plan = latest_matching_file(root_path / "agent-plans", ["*-agent-finish-plan.json"])
    latest_agent_proposals = latest_matching_file(root_path / "agent-plans", ["*-agent-proposals.json"])
    latest_duplicate_report = latest_matching_file(root_path / "reports", ["*-duplicate-report.json"])
    latest_link_check_report = latest_matching_file(root_path / "reports", ["*-link-check-report.json"])
    latest_garden_suggestions = latest_matching_file(root_path / "reports", ["*-garden-suggestions.json"])

    latest_search_results = latest_matching_file(root_path / "search", ["*-search-results.json"])
    latest_project_brief = latest_matching_file(root_path / "briefs", ["*-project-brief.md"])
    latest_hub_map = latest_matching_file(root_path / "Maps", ["Emerging Hubs.md"])
    has_metadata = vault_has_metadata(vault_path, root)

    return {
        "vault": vault_path,
        "root": root,
        "counts": {
            "total": total,
            "drift": drift,
            "reef": reef,
            "pearls": pearls,
            "discarded": discarded,
        },
        "latest_review_session": latest_review_session,
        "latest_review_decisions": latest_review_decisions,
        "latest_agent_plan": latest_agent_plan,
        "latest_agent_proposals": latest_agent_proposals,
        "latest_duplicate_report": latest_duplicate_report,
        "latest_link_check_report": latest_link_check_report,
        "latest_garden_suggestions": latest_garden_suggestions,

        "latest_search_results": latest_search_results,
        "latest_project_brief": latest_project_brief,
        "latest_hub_map": latest_hub_map,
        "next_action": recommended_next_action(
            total,
            drift,
            latest_review_session,
            latest_review_decisions,
            latest_agent_plan,
            latest_agent_proposals,
            latest_duplicate_report,
            latest_link_check_report,
            latest_garden_suggestions,
            has_metadata,
        ),
    }


def recommended_next_action(
    total: int,
    drift: int,
    latest_review_session: Path | None,
    latest_review_decisions: Path | None,
    latest_agent_plan: Path | None,
    latest_agent_proposals: Path | None,
    latest_duplicate_report: Path | None,
    latest_link_check_report: Path | None,
    latest_garden_suggestions: Path | None,
    has_metadata: bool,
) -> str:
    if total == 0:
        return "Import bookmarks, a URL list, or a CSV file to create your first Drops."
    if total > 0 and latest_duplicate_report is None:
        return "Create a duplicate report, then continue reviewing Drift Drops."
    if total > 0 and latest_link_check_report is None:
        return "Check saved links so broken URLs do not waste review time."
    if total > 0 and latest_link_check_report is not None and not has_metadata:
        return "Refresh metadata, then export a review session JSON."
    if total > 0 and has_metadata and latest_garden_suggestions is None:
        return "Create garden suggestions from curated project and shoal examples."
    if drift > 0 and latest_review_session is None:
        return "Export a review session JSON, then open Review Mode."
    if drift > 0 and latest_review_decisions is None:
        return "Open Review Mode, review a sample, and export review decisions JSON."
    if latest_review_decisions is not None and latest_agent_plan is None:
        return "Apply review decisions, then create an agent finish plan."
    if latest_agent_plan is not None and latest_agent_proposals is None:
        return "Draft agent proposals from the latest agent finish plan."
    if latest_agent_proposals is not None:
        return "Dry run apply-agent-proposals, then apply accepted Agent proposals."
    return "Continue reviewing Drift Drops in Review Mode."


def render_app_dashboard(state: dict[str, object]) -> str:
    vault = state["vault"]
    if not isinstance(vault, Path):
        vault = Path(str(vault))
    root = str(state["root"])
    counts = state.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}

    latest_review_session = relative_or_none(state.get("latest_review_session"), vault)
    latest_review_decisions = relative_or_none(state.get("latest_review_decisions"), vault)
    latest_agent_plan = relative_or_none(state.get("latest_agent_plan"), vault)
    latest_agent_proposals = relative_or_none(state.get("latest_agent_proposals"), vault)
    latest_duplicate_report = relative_or_none(state.get("latest_duplicate_report"), vault)
    latest_link_check_report = relative_or_none(state.get("latest_link_check_report"), vault)
    latest_garden_suggestions = relative_or_none(state.get("latest_garden_suggestions"), vault)

    latest_search_results = relative_or_none(state.get("latest_search_results"), vault)
    latest_project_brief = relative_or_none(state.get("latest_project_brief"), vault)
    latest_hub_map = relative_or_none(state.get("latest_hub_map"), vault)
    next_action = html_escape(str(state.get("next_action", "Continue.")))
    vault_text = html_escape(str(vault))

    def count(name: str) -> str:
        return html_escape(str(counts.get(name, 0)))

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>MemoReef local app</title>
  <style>
    {app_common_css()}
    main {{ width:min(1080px, calc(100% - 32px)); }}
    header {{ margin-bottom:24px; }}
    .eyebrow {{ color:var(--green); text-transform:uppercase; letter-spacing:.16em; font-size:12px; font-weight:800; }}
    .grid {{ display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:12px; margin:24px 0; }}
    .stat {{ border:1px solid var(--line); border-radius:8px; background:linear-gradient(180deg, var(--panel), var(--panel2)); box-shadow:0 22px 70px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.045); }}
    .stat {{ padding:18px; }}
    .stat strong {{ display:block; font-size:34px; letter-spacing:-.05em; }}
    .stat span {{ color:var(--muted); font-size:13px; }}
    .sections {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
    .next {{ border-color:rgba(117,234,211,.38); }}
    dl {{ margin:0; }}
    .workflow ol {{ margin:0; padding-left:20px; color:var(--muted); }}
    .workflow li {{ margin:8px 0; }}
    @media (max-width:760px) {{ .grid, .sections {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    {app_nav("dashboard")}
    <header>
      <div class=\"eyebrow\">MemoReef local app</div>
      <h1>Your source reef, locally visible.</h1>
      <p>Vault: <code>{vault_text}</code> · Root: <code>{html_escape(root)}</code></p>
    </header>

    <section class=\"grid\" aria-label=\"MemoReef counts\">
      <div class=\"stat\"><strong>{count('total')}</strong><span>Total Drops</span></div>
      <div class=\"stat\"><strong>{count('drift')}</strong><span>Drift</span></div>
      <div class=\"stat\"><strong>{count('reef')}</strong><span>Reef</span></div>
      <div class=\"stat\"><strong>{count('pearls')}</strong><span>Pearls</span></div>
      <div class=\"stat\"><strong>{count('discarded')}</strong><span>Discarded</span></div>
    </section>

    <section class=\"sections\">
      <div class=\"card next\">
        <h2>Next recommended action</h2>
        <p>{next_action}</p>
      </div>
      <div class=\"card\">
        <h2>Product tour</h2>
        <p>Open <a href=\"tour.html\">tour.html</a> for a guided story generated from this vault: the mess, the value, Drop detail pages, reports, briefs, review handoff, library search, and why local Markdown matters.</p>
      </div>
      <div class=\"card\">
        <h2>Latest local artifacts</h2>
        <dl>
          <dt>Review session JSON</dt><dd>{html_escape(latest_review_session)}</dd>
          <dt>Review decisions JSON</dt><dd>{html_escape(latest_review_decisions)}</dd>
          <dt>Agent finish plan</dt><dd>{html_escape(latest_agent_plan)}</dd>
          <dt>Agent proposals</dt><dd>{html_escape(latest_agent_proposals)}</dd>
          <dt>Duplicate report</dt><dd>{html_escape(latest_duplicate_report)}</dd>
          <dt>Link check report</dt><dd>{html_escape(latest_link_check_report)}</dd>
          <dt>Garden suggestions</dt><dd>{html_escape(latest_garden_suggestions)}</dd>

          <dt>Library search</dt><dd>{html_escape(latest_search_results)}</dd>
          <dt>Project brief</dt><dd>{html_escape(latest_project_brief)}</dd>
          <dt>Hub map</dt><dd>{html_escape(latest_hub_map)}</dd>
        </dl>
      </div>
      <div class=\"card workflow\">
        <h2>Workflow</h2>
        <ol>
          <li>Import links into Markdown Drops.</li>
          <li>Run <code>duplicate-report</code> to spot exact URL, same-domain, and similar-title clutter.</li>
          <li>Run <code>check-links</code> to find broken, suspicious, or unreachable saved URLs.</li>
          <li>Run <code>refresh-metadata</code> to fetch titles, descriptions, canonical URLs, and hostnames.</li>
          <li>Run <code>suggest-gardens</code> to propose existing projects and shoals for unsorted Drops.</li>
          <li>Review the suggestions JSON, then run <code>apply-garden-suggestions --dry-run</code> before applying accepted labels.</li>

          <li>Run <code>search-library</code> to search the local Library, then open <code>library.html</code>.</li>
          <li>Run <code>brief --project "AI Agents"</code> to export selected Drops into an agent-ready Markdown project brief.</li>
          <li>Run <code>hub-map</code> to create Obsidian map notes and Drop-to-hub graph links.</li>
          <li>Open <code>briefs.html</code> and <code>reports.html</code> to inspect generated handoff Markdown and local report JSON.</li>
          <li>Run <code>export-review-session</code> with optional filtered review queues like <code>--project</code>, <code>--shoal</code>, or <code>--pearl-only</code>, then open <code>site/swipe.html</code> for Review Mode.</li>
          <li>Export decisions from Review Mode, then run <code>apply-review-decisions</code>.</li>
          <li>Create an agent finish plan with <code>plan-agent-finish</code>.</li>
          <li>Draft Agent proposals with <code>draft-agent-proposals</code>.</li>
          <li>Dry run accepted Agent proposal updates with <code>apply-agent-proposals --dry-run</code>, then apply deliberately.</li>
        </ol>
      </div>
      <div class=\"card\">
        <h2>Library/Search</h2>
        <p>Open <a href=\"library.html\">library.html</a> for local search guidance, the latest saved search results, and links to generated Drop detail pages.</p>
      </div>
      <div class=\"card\">
        <h2>Review Mode</h2>
        <p>Open <a href=\"review.html\">review.html</a> for the browser-only Review Mode launcher and the exact apply command. The static app never writes review decisions directly.</p>
        <p>Reports are summarized on <a href=\"reports.html\">reports.html</a>; project briefs are listed on <a href=\"briefs.html\">briefs.html</a>.</p>
        <p>This dashboard is static HTML. No backend, no network, no subscription.</p>
      </div>
    </section>
  </main>
</body>
</html>
"""


APP_NAV_ITEMS = [
    ("dashboard", "Dashboard", "index.html"),
    ("pilot", "Pilot", "pilot.html"),
    ("tour", "Tour", "tour.html"),
    ("library", "Library", "library.html"),
    ("review", "Review", "review.html"),
    ("reports", "Reports", "reports.html"),
    ("briefs", "Briefs", "briefs.html"),
]


def app_nav(current: str, prefix: str = "") -> str:
    links = []
    for key, label, href in APP_NAV_ITEMS:
        current_attr = ' aria-current="page"' if key == current else ""
        links.append(f'<a href="{html_escape(prefix + href)}"{current_attr}>{html_escape(label)}</a>')
    return '<nav class="app-nav" aria-label="MemoReef app navigation">' + "".join(links) + "</nav>"


def app_common_css() -> str:
    return """
    :root { color-scheme: dark; --bg:#061118; --bg2:#0a1b24; --panel:rgba(12,31,40,.82); --panel2:rgba(6,19,27,.72); --line:rgba(190,242,255,.14); --text:#edf8f8; --muted:#9eb5bb; --dim:#6e878e; --pearl:#f1e6cc; --green:#75ead3; --coral:#ff927e; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:radial-gradient(circle at 12% -10%, rgba(117,234,211,.14), transparent 24rem), radial-gradient(circle at 85% 8%, rgba(255,146,126,.08), transparent 20rem), linear-gradient(180deg, var(--bg2), var(--bg)); color:var(--text); }
    body::before { content:""; position:fixed; inset:0; pointer-events:none; background:linear-gradient(180deg, rgba(255,255,255,.035), transparent 38%), linear-gradient(90deg, rgba(255,255,255,.018) 1px, transparent 1px), linear-gradient(rgba(255,255,255,.018) 1px, transparent 1px); background-size:auto, 72px 72px, 72px 72px; mask-image:linear-gradient(to bottom, rgba(0,0,0,.75), transparent 78%); }
    body::after { content:""; position:fixed; right:-120px; top:10vh; width:420px; height:760px; pointer-events:none; border-left:1px solid rgba(117,234,211,.12); border-top:1px solid rgba(255,146,126,.08); border-radius:55% 0 0 45%; transform:rotate(13deg); box-shadow:-34px 0 90px rgba(117,234,211,.055); mask-image:linear-gradient(to bottom, transparent, #000 18%, #000 72%, transparent); }
    main { width:min(1040px, calc(100% - 32px)); margin:0 auto; padding:34px 0 58px; position:relative; }
    a { color:var(--green); text-decoration-thickness:1px; text-underline-offset:3px; }
    h1 { font-size:clamp(34px, 6.8vw, 66px); line-height:.95; margin:.22em 0 .18em; letter-spacing:-.055em; }
    h2 { margin:0 0 10px; font-size:clamp(20px, 2.6vw, 28px); line-height:1.05; letter-spacing:-.035em; }
    p, li { color:var(--muted); line-height:1.58; }
    strong { color:var(--text); }
    code { color:var(--pearl); overflow-wrap:anywhere; }
    pre { border:1px solid rgba(241,230,204,.15); border-radius:8px; background:rgba(0,0,0,.22); padding:14px; overflow:auto; }
    .app-nav { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 28px; padding:8px; border:1px solid rgba(190,242,255,.1); border-radius:8px; background:rgba(4,14,21,.42); }
    .app-nav a { color:var(--muted); text-decoration:none; border:1px solid transparent; border-radius:6px; padding:8px 11px; background:transparent; font-size:14px; }
    .app-nav a:hover { color:var(--text); border-color:var(--line); background:rgba(255,255,255,.04); }
    .app-nav a[aria-current="page"] { color:#061118; background:var(--green); border-color:var(--green); }
    .panel, .result, .card { border:1px solid var(--line); border-radius:8px; background:linear-gradient(180deg, var(--panel), var(--panel2)); padding:22px; margin:16px 0; box-shadow:0 22px 70px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.045); }
    .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }
    .meta { color:var(--muted); font-size:14px; }
    dl { display:grid; grid-template-columns:minmax(130px, 190px) 1fr; gap:10px 16px; }
    dt { color:var(--dim); font-size:11px; text-transform:uppercase; letter-spacing:.14em; font-weight:760; }
    dd { margin:0; overflow-wrap:anywhere; }
    ul, ol { padding-left:22px; }
    @media (max-width:760px) { .grid, dl { grid-template-columns:1fr; } }
    """


def drop_detail_filename(drop: dict[str, object]) -> str:
    return f"{slug_for_filename(str(drop.get('path') or drop.get('title') or 'drop'))}.html"


def drop_detail_href(drop: dict[str, object], prefix: str = "drops/") -> str:
    return prefix + drop_detail_filename(drop)


def drop_detail_href_for_path(path: object, prefix: str = "drops/") -> str | None:
    if not isinstance(path, str) or not path.strip():
        return None
    return prefix + f"{slug_for_filename(path)}.html"


def app_drop_items(vault: Path, root: str = "MemoReef") -> list[dict[str, object]]:
    vault_path = vault.expanduser().resolve()
    drops_dir = vault_path / root / "Drops"
    drops: list[dict[str, object]] = []
    if not drops_dir.exists():
        return drops
    for path in sorted(drops_dir.rglob("*.md")):
        drops.append(brief_item_from_drop(path, vault_path))
    return drops


def format_label_list(value: object) -> str:
    if isinstance(value, list) and value:
        return ", ".join(str(item) for item in value)
    return "none"


def latest_search_payload(vault: Path, root: str = "MemoReef") -> dict[str, object] | None:
    path = latest_matching_file(vault / root / "search", ["*-search-results.json"])
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def render_library_page(vault: Path, root: str = "MemoReef") -> str:
    payload = latest_search_payload(vault, root)
    query = ""
    matches = 0
    items: list[object] = []
    if payload is not None:
        query = str(payload.get("query") or "")
        summary = payload.get("summary", {})
        if isinstance(summary, dict):
            matches = int(summary.get("matches", 0))
        raw_items = payload.get("items", [])
        if isinstance(raw_items, list):
            items = raw_items[:10]

    result_cards = []
    for item in items:
        if not isinstance(item, dict):
            continue
        projects = ", ".join(str(value) for value in item.get("projects", [])) if isinstance(item.get("projects"), list) else ""
        shoals = ", ".join(str(value) for value in item.get("shoals", [])) if isinstance(item.get("shoals"), list) else ""
        pearl = "Pearl" if item.get("pearl") else "Drop"
        detail_href = drop_detail_href_for_path(item.get("path"))
        detail_link = f'<p><a href="{html_escape(detail_href)}">Open Drop detail</a></p>' if detail_href else ""
        result_cards.append(
            f"""
      <article class=\"result\">
        <h2>{html_escape(str(item.get('title') or 'Untitled'))}</h2>
        <p class=\"meta\">{html_escape(str(item.get('hostname') or ''))} · {html_escape(str(item.get('status') or 'drift'))} · {pearl}</p>
        <p>{html_escape(str(item.get('snippet') or ''))}</p>
        <p class=\"meta\">Projects: {html_escape(projects or 'none')} · Shoals: {html_escape(shoals or 'none')}</p>
        {detail_link}
      </article>"""
        )
    results_html = "\n".join(result_cards) if result_cards else "<p>No saved search results yet.</p>"

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>MemoReef Library Search</title>
  <style>
    {app_common_css()}
    .result h2 {{ margin:0 0 6px; }}
  </style>
</head>
<body>
  <main>
    {app_nav("library")}
    <h1>Library/Search</h1>
    <section class=\"panel\">
      <p>Search your local Markdown Drops without a backend:</p>
      <p><code>python3 -m memoreef.cli search-library --vault {html_escape(str(vault))} --query "agent workflow"</code></p>
      <p>Use filters such as <code>--project</code>, <code>--shoal</code>, <code>--tag</code>, <code>--hostname</code>, <code>--pearl-only</code>, and <code>--exclude-status</code> to focus the Library.</p>
    </section>
    <section class=\"panel\">
      <h2>Latest search</h2>
      <p>Query: <code>{html_escape(query or 'none')}</code> · Matches: <strong>{matches}</strong></p>
    </section>
    {results_html}
  </main>
</body>
</html>
"""


def render_drop_detail_page(vault: Path, root: str, drop: dict[str, object]) -> str:
    app_dir = vault / root / "app"
    drop_path = vault / str(drop.get("path") or "")
    markdown_href = app_href(drop_path, app_dir) or ""
    markdown_link = f'<a href="{html_escape(markdown_href)}">{html_escape(str(drop.get("path") or ""))}</a>' if markdown_href else html_escape(str(drop.get("path") or ""))
    url = str(drop.get("url") or "")
    url_html = f'<a href="{html_escape(url)}">{html_escape(url)}</a>' if url else "none"
    summary = str(drop.get("summary") or drop.get("page_description") or "").strip()
    notes = str(drop.get("notes") or "").strip()
    agent_brief = str(drop.get("agent_brief") or "").strip()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_escape(str(drop.get('title') or 'MemoReef Drop'))}</title>
  <style>
    {app_common_css()}
    pre {{ white-space:pre-wrap; color:var(--muted); line-height:1.55; font-family:inherit; }}
  </style>
</head>
<body>
  <main>
    {app_nav("library", "../")}
    <p><a href="../library.html">Back to library</a> · <a href="../tour.html">Tour</a></p>
    <h1>{html_escape(str(drop.get('title') or 'Untitled Drop'))}</h1>
    <section class="panel">
      <dl>
        <dt>URL</dt><dd>{url_html}</dd>
        <dt>Status</dt><dd>{html_escape(str(drop.get('status') or 'drift'))}</dd>
        <dt>Pearl</dt><dd>{'yes' if bool(drop.get('pearl', False)) else 'no'}</dd>
        <dt>Tags</dt><dd>{html_escape(format_label_list(drop.get('tags')))}</dd>
        <dt>Projects</dt><dd>{html_escape(format_label_list(drop.get('projects')))}</dd>
        <dt>Shoals</dt><dd>{html_escape(format_label_list(drop.get('shoals')))}</dd>
        <dt>Hostname</dt><dd>{html_escape(str(drop.get('hostname') or 'none'))}</dd>
        <dt>Markdown path</dt><dd>{markdown_link}</dd>
      </dl>
    </section>
    <section class="panel">
      <h2>Summary</h2>
      <p>{html_escape(summary or 'No summary found in this Drop.')}</p>
    </section>
    <section class="panel">
      <h2>Notes</h2>
      <pre>{html_escape(notes or 'No notes found in this Drop.')}</pre>
    </section>
    <section class="panel">
      <h2>Agent brief</h2>
      <pre>{html_escape(agent_brief or 'No agent brief found in this Drop.')}</pre>
    </section>
  </main>
</body>
</html>
"""


def brief_title_and_summary(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip() or title
            break
    source_count = None
    filters = None
    for line in text.splitlines():
        match = re.match(r"- Selected sources:\s*(\d+)", line)
        if match:
            source_count = int(match.group(1))
        if line.startswith("- Applied filters:"):
            filters = line.split(":", 1)[1].strip()
    return {"title": title, "source_count": source_count, "filters": filters}


def render_briefs_page(vault: Path, root: str = "MemoReef") -> str:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    app_dir = root_path / "app"
    brief_paths = sorted(
        [path for path in (root_path / "briefs").glob("*.md") if path.is_file()] if (root_path / "briefs").exists() else [],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    cards = []
    for path in brief_paths:
        summary = brief_title_and_summary(path)
        href = app_href(path, app_dir) or ""
        source_count = summary.get("source_count")
        source_text = str(source_count) if source_count is not None else "unknown"
        cards.append(
            f"""
      <article class="card">
        <h2>{html_escape(str(summary.get('title') or path.stem))}</h2>
        <p class="meta"><a href="{html_escape(href)}">{html_escape(path.resolve().relative_to(vault_path).as_posix())}</a></p>
        <p>Sources: <strong>{html_escape(source_text)}</strong> · Filters: <code>{html_escape(str(summary.get('filters') or 'unknown'))}</code></p>
      </article>"""
        )
    cards_html = "\n".join(cards) if cards else "<p>No project brief Markdown files were detected yet.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemoReef Project Briefs</title>
  <style>{app_common_css()}</style>
</head>
<body>
  <main>
    {app_nav("briefs")}
    <h1>Project briefs</h1>
    <section class="panel">
      <p>MemoReef project brief Markdown files are local, readable handoff documents generated from selected Drops.</p>
      <p><code>python3 -m memoreef.cli brief --vault {html_escape(str(vault_path))} --project "AI Agents"</code></p>
    </section>
    {cards_html}
  </main>
</body>
</html>
"""


def report_summary(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"kind": "report", "summary": "unparseable JSON"}
    if not isinstance(payload, dict):
        return {"kind": "report", "summary": "unparseable JSON"}
    name = path.name
    if "duplicate" in name:
        kind = "duplicate report"
    elif "link-check" in name:
        kind = "link-check report"
    elif "garden" in name:
        kind = "garden suggestions"
    elif "metadata" in name:
        kind = "metadata report"
    else:
        kind = "local report"
    summary = payload.get("summary")
    if isinstance(summary, dict):
        useful = ", ".join(f"{key}={value}" for key, value in sorted(summary.items()))
    else:
        useful = "no summary object"
    return {"kind": kind, "summary": useful}


def render_reports_page(vault: Path, root: str = "MemoReef") -> str:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    app_dir = root_path / "app"
    reports_dir = root_path / "reports"
    report_paths = sorted(
        [path for path in reports_dir.glob("*.json") if path.is_file()] if reports_dir.exists() else [],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    cards = []
    for path in report_paths:
        summary = report_summary(path)
        href = app_href(path, app_dir) or ""
        cards.append(
            f"""
      <article class="card">
        <h2>{html_escape(str(summary.get('kind') or 'local report'))}</h2>
        <p class="meta"><a href="{html_escape(href)}">{html_escape(path.resolve().relative_to(vault_path).as_posix())}</a></p>
        <p>{html_escape(str(summary.get('summary') or 'no summary'))}</p>
      </article>"""
        )
    cards_html = "\n".join(cards) if cards else "<p>No local report JSON files were detected yet.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemoReef Reports</title>
  <style>{app_common_css()}</style>
</head>
<body>
  <main>
    {app_nav("reports")}
    <h1>Reports</h1>
    <section class="panel">
      <p>Local reports surface duplicate groups, link-check results, garden suggestions, and metadata-related JSON when present.</p>
    </section>
    {cards_html}
  </main>
</body>
</html>
"""


def render_review_page(vault: Path, root: str = "MemoReef") -> str:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    app_dir = root_path / "app"
    session_paths = sorted(
        [path for path in (root_path / "review-sessions").glob("*.json") if path.is_file()] if (root_path / "review-sessions").exists() else [],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    decision_paths = sorted(
        [path for path in vault_path.rglob("*review-decisions*.json") if path.is_file()],
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )

    def artifact_list(paths: list[Path]) -> str:
        if not paths:
            return "<p>None detected yet.</p>"
        items = []
        for path in paths:
            href = app_href(path, app_dir) or ""
            items.append(f'<li><a href="{html_escape(href)}">{html_escape(path.resolve().relative_to(vault_path).as_posix())}</a></li>')
        return "<ul>" + "".join(items) + "</ul>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemoReef Review Mode</title>
  <style>{app_common_css()}</style>
</head>
<body>
  <main>
    {app_nav("review")}
    <h1>Review Mode</h1>
    <section class="panel">
      <p>Review Mode is browser-only in v0.2. This static app can list local files, but it cannot write decisions to the filesystem directly.</p>
      <ol>
        <li>Open the repo file <code>site/swipe.html</code> in your browser.</li>
        <li>Load a review-session JSON file with the page file picker.</li>
        <li>Review Drops and export a decisions JSON file from the browser.</li>
        <li>Apply decisions with <code>python3 -m memoreef.cli apply-review-decisions --vault {html_escape(str(vault_path))} --decisions /path/to/memoreef-review-decisions.json</code>.</li>
      </ol>
    </section>
    <section class="grid">
      <div class="card">
        <h2>Review-session JSON</h2>
        {artifact_list(session_paths)}
      </div>
      <div class="card">
        <h2>Review-decision JSON</h2>
        {artifact_list(decision_paths)}
      </div>
    </section>
  </main>
</body>
</html>
"""


def render_pilot_page(vault: Path, root: str = "MemoReef") -> str:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    app_dir = root_path / "app"
    state = dashboard_state(vault_path, root)
    counts = state.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    pilot_readme = root_path / "PILOT_README.md"
    latest_review_session = state.get("latest_review_session")
    latest_duplicate_report = state.get("latest_duplicate_report")
    latest_project_brief = state.get("latest_project_brief")
    latest_hub_map = state.get("latest_hub_map")
    review_mode = repo_root() / "site" / "swipe.html"

    detected = [
        f"{counts.get('total', 0)} Markdown Drops",
        f"{counts.get('drift', 0)} Drift items ready for review",
        "Pilot README detected" if pilot_readme.exists() else "No PILOT_README.md detected yet",
        "Review session detected" if isinstance(latest_review_session, Path) else "No review session detected yet",
        "Duplicate report detected" if isinstance(latest_duplicate_report, Path) else "No duplicate report detected yet",
        "Project brief detected" if isinstance(latest_project_brief, Path) else "No project brief detected yet",
    ]
    review_session_text = str(latest_review_session) if isinstance(latest_review_session, Path) else str(root_path / "review-sessions")
    duplicate_link = linked_file("Latest duplicate report JSON", latest_duplicate_report, app_dir)
    readme_link = linked_file("Open pilot Markdown checklist", pilot_readme, app_dir)
    brief_link = linked_file("Latest project brief", latest_project_brief, app_dir)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemoReef Pilot Checklist</title>
  <style>{app_common_css()}</style>
</head>
<body>
  <main>
    {app_nav("pilot")}
    <h1>Pilot checklist</h1>
    <section class="panel">
      <h2>Start here</h2>
      <p>This page is the guided local pilot surface. It shows what MemoReef generated, which files to open, how to review a few Drops, and what feedback to send back.</p>
      <p>Vault: <code>{html_escape(str(vault_path))}</code></p>
      {readme_link}
    </section>
    <section class="grid">
      <div class="card">
        <h2>Generated or detected</h2>
        {html_list(detected)}
        {duplicate_link}
      </div>
      <div class="card">
        <h2>Open these files</h2>
        <p><code>{html_escape(str(app_dir / "pilot.html"))}</code></p>
        <p><code>{html_escape(str(app_dir / "tour.html"))}</code></p>
        <p><code>{html_escape(str(app_dir / "index.html"))}</code></p>
        <p><code>{html_escape(str(app_dir / "review.html"))}</code></p>
      </div>
    </section>
    <section class="panel">
      <h2>Review Mode</h2>
      <ol>
        <li>Open <code>{html_escape(str(review_mode))}</code> in your browser.</li>
        <li>Use the file picker to load this review-session JSON: <code>{html_escape(review_session_text)}</code>.</li>
        <li>Review a few items and export decisions from the browser.</li>
        <li>Apply them with <code>python3 -m memoreef.cli apply-review-decisions --vault {html_escape(str(vault_path))} --root {html_escape(root)} --decisions /path/to/memoreef-review-decisions.json</code>.</li>
        <li>Regenerate pages with <code>python3 -m memoreef.cli app --vault {html_escape(str(vault_path))} --root {html_escape(root)}</code>.</li>
      </ol>
    </section>
    <section class="panel">
      <h2>Project brief</h2>
      <p>After review, create a local Markdown brief for a project or a small sample of sources:</p>
      <p><code>python3 -m memoreef.cli brief --vault {html_escape(str(vault_path))} --root {html_escape(root)} --limit 10</code></p>
      <p><code>python3 -m memoreef.cli app --vault {html_escape(str(vault_path))} --root {html_escape(root)}</code></p>
      {brief_link}
    </section>
    <section class="panel">
      <h2>Feedback</h2>
      <ul>
        <li>Did import succeed with your real export?</li>
        <li>Which step was confusing?</li>
        <li>Did you find sources worth keeping?</li>
        <li>Which source details were missing?</li>
        <li>What feature did you expect but not find?</li>
        <li>Would you use MemoReef again for your saved links?</li>
      </ul>
      <p>Privacy reminder: this pilot is offline-only. Files stay local; no backend, network call, AI call, account, or server is used.</p>
    </section>
  </main>
</body>
</html>
"""


def read_json_object(path: object) -> dict[str, object] | None:
    if not isinstance(path, Path) or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def app_href(path: object, app_dir: Path) -> str | None:
    if not isinstance(path, Path) or not path.exists():
        return None
    return os.path.relpath(path.resolve(), app_dir.resolve()).replace(os.sep, "/")


def linked_file(label: str, path: object, app_dir: Path) -> str:
    href = app_href(path, app_dir)
    if href is None:
        return ""
    return f'<p><a href="{html_escape(href)}">{html_escape(label)}</a></p>'


def html_list(items: list[str]) -> str:
    if not items:
        return ""
    return "<ul>" + "".join(f"<li>{html_escape(item)}</li>" for item in items) + "</ul>"


def top_values(drops: list[dict[str, object]], key: str, limit: int = 4) -> list[str]:
    counts: dict[str, int] = {}
    for drop in drops:
        values = drop.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            text = str(value).strip()
            if text and text != "[]":
                counts[text] = counts.get(text, 0) + 1
    return [name for name, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def drop_titles(drops: list[dict[str, object]], limit: int = 4) -> list[str]:
    titles = [str(drop.get("title") or "").strip() for drop in drops]
    return [title for title in titles if title][:limit]


def payload_items(payload: dict[str, object] | None, key: str = "items") -> list[dict[str, object]]:
    if payload is None:
        return []
    raw_items = payload.get(key, [])
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]


def render_tour_page(vault: Path, root: str = "MemoReef") -> str:
    vault_path = vault.expanduser().resolve()
    root_path = vault_path / root
    app_dir = root_path / "app"
    state = dashboard_state(vault_path, root)
    counts = state.get("counts", {})
    if not isinstance(counts, dict):
        counts = {}
    drops = load_garden_drop_items(vault_path, root)
    title_examples = drop_titles(drops, 5)
    pearl_titles = drop_titles([drop for drop in drops if bool(drop.get("pearl"))], 4)
    reef_titles = drop_titles([drop for drop in drops if str(drop.get("status") or "") in {"reef", "deep"}], 4)
    projects = top_values(drops, "projects")
    shoals = top_values(drops, "shoals")

    duplicate_payload = read_json_object(state.get("latest_duplicate_report"))
    link_payload = read_json_object(state.get("latest_link_check_report"))
    garden_payload = read_json_object(state.get("latest_garden_suggestions"))
    review_payload = read_json_object(state.get("latest_review_session"))
    decisions_payload = read_json_object(state.get("latest_review_decisions"))
    agent_plan_payload = read_json_object(state.get("latest_agent_plan"))
    agent_proposals_payload = read_json_object(state.get("latest_agent_proposals"))
    search_payload = read_json_object(state.get("latest_search_results"))
    latest_project_brief = state.get("latest_project_brief")
    latest_hub_map = state.get("latest_hub_map")

    mess_signals = [
        f"{counts.get('total', 0)} total Drops in local Markdown.",
        f"{counts.get('drift', 0)} still in Drift for review.",
        f"{counts.get('discarded', 0)} already discarded so they do not pollute the Reef.",
    ]
    if duplicate_payload is not None:
        summary = duplicate_payload.get("summary", {})
        if isinstance(summary, dict):
            mess_signals.append(
                "Duplicate report: "
                f"{summary.get('exact_url_groups', 0)} exact URL groups, "
                f"{summary.get('same_domain_groups', 0)} same-domain groups, "
                f"{summary.get('similar_title_groups', 0)} similar-title groups."
            )
    if link_payload is not None:
        summary = link_payload.get("summary", {})
        if isinstance(summary, dict):
            mess_signals.append(
                "Link check report: "
                f"{summary.get('broken', 0)} broken, {summary.get('suspicious', 0)} suspicious, "
                f"{summary.get('unknown', 0)} unknown."
            )
    if garden_payload is not None:
        summary = garden_payload.get("summary", {})
        if isinstance(summary, dict):
            mess_signals.append(f"Garden suggestions found {summary.get('suggestions', 0)} Drops that may fit existing projects or shoals.")

    value_signals = [
        f"{counts.get('reef', 0)} Drops are already in the Reef.",
        f"{counts.get('pearls', 0)} are marked as Pearls.",
    ]
    if projects:
        value_signals.append(f"Projects detected: {', '.join(projects)}.")
    if shoals:
        value_signals.append(f"Shoals detected: {', '.join(shoals)}.")

    review_lines: list[str] = []
    if review_payload is not None:
        stats = review_payload.get("stats", {})
        if isinstance(stats, dict):
            review_lines.append(f"Latest review session contains {stats.get('total', 0)} Drops, including {stats.get('drift', 0)} Drift items.")
        review_titles = drop_titles(payload_items(review_payload), 3)
        if review_titles:
            review_lines.append(f"Review examples: {', '.join(review_titles)}.")
    if decisions_payload is not None:
        decisions = decisions_payload.get("decisions", [])
        if isinstance(decisions, list):
            counts_by_decision: dict[str, int] = {}
            for decision in decisions:
                if isinstance(decision, dict):
                    name = str(decision.get("decision") or "unknown")
                    counts_by_decision[name] = counts_by_decision.get(name, 0) + 1
            review_lines.append("Review decisions recorded: " + ", ".join(f"{key}={value}" for key, value in sorted(counts_by_decision.items())) + ".")
    if agent_plan_payload is not None:
        summary = agent_plan_payload.get("summary", {})
        if isinstance(summary, dict):
            review_lines.append(f"Agent finish plan: {summary.get('reviewed', 0)} reviewed examples and {summary.get('remaining', 0)} remaining Drops.")
    if agent_proposals_payload is not None:
        summary = agent_proposals_payload.get("summary", {})
        if isinstance(summary, dict):
            review_lines.append(f"Agent proposals: {summary.get('proposed', 0)} drafted, {summary.get('needs_review', 0)} needing review.")
    if isinstance(latest_project_brief, Path):
        review_lines.append("Latest project brief detected for agent or human handoff.")

    library_lines: list[str] = []
    if search_payload is not None:
        summary = search_payload.get("summary", {})
        matches = summary.get("matches", 0) if isinstance(summary, dict) else 0
        query = str(search_payload.get("query") or "")
        library_lines.append(f'Latest local search for "{query}" returned {matches} matches.')
        search_titles = drop_titles(payload_items(search_payload), 4)
        if search_titles:
            library_lines.append(f"Search examples: {', '.join(search_titles)}.")
    else:
        library_lines.append("No saved search result was detected yet; run search-library to create one.")
    if isinstance(latest_project_brief, Path):
        library_lines.append("A Markdown project brief is available from selected local Drops.")
    detail_examples = [
        f'<a href="{html_escape(drop_detail_href(drop))}">{html_escape(str(drop.get("title") or "Untitled"))}</a>'
        for drop in drops[:5]
    ]

    artifact_links = "\n".join(
        link
        for link in [
            linked_file("Open dashboard", app_dir / "index.html", app_dir),
            linked_file("Open library search page", app_dir / "library.html", app_dir),
            linked_file("Open Review Mode launcher", app_dir / "review.html", app_dir),
            linked_file("Open reports page", app_dir / "reports.html", app_dir),
            linked_file("Open project briefs page", app_dir / "briefs.html", app_dir),
            linked_file("Latest review session JSON", state.get("latest_review_session"), app_dir),
            linked_file("Latest duplicate report JSON", state.get("latest_duplicate_report"), app_dir),
            linked_file("Latest link check report JSON", state.get("latest_link_check_report"), app_dir),
            linked_file("Latest garden suggestions JSON", state.get("latest_garden_suggestions"), app_dir),
            linked_file("Latest search results JSON", state.get("latest_search_results"), app_dir),
            linked_file("Latest project brief Markdown", state.get("latest_project_brief"), app_dir),
            linked_file("Latest hub map Markdown", latest_hub_map, app_dir),
            linked_file("Latest agent finish plan JSON", state.get("latest_agent_plan"), app_dir),
            linked_file("Latest agent proposals JSON", state.get("latest_agent_proposals"), app_dir),
            linked_file("Latest review decisions JSON", state.get("latest_review_decisions"), app_dir),
        ]
        if link
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MemoReef Product Tour</title>
  <style>
    {app_common_css()}
    .lede {{ max-width:760px; font-size:18px; }}
    .stats {{ display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:12px; margin:24px 0; }}
    .stat, section {{ border:1px solid var(--line); background:linear-gradient(180deg, var(--panel), var(--panel2)); border-radius:8px; box-shadow:0 22px 70px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.045); }}
    .stat {{ padding:16px; }}
    .stat strong {{ display:block; font-size:34px; }}
    .stat span {{ color:var(--muted); font-size:13px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
    section {{ padding:22px; }}
    ul {{ margin:10px 0 0; padding-left:20px; }}
    .wide {{ grid-column:1 / -1; }}
    @media (max-width:780px) {{ .stats, .grid {{ grid-template-columns:1fr; }} .wide {{ grid-column:auto; }} }}
  </style>
</head>
<body>
  <main>
    {app_nav("tour")}
    <h1>Messy saves become source memory.</h1>
    <p class="lede">This static tour was generated from the current vault. It shows why MemoReef exists: scattered saves become reviewed local Markdown, useful Pearls, clutter reports, agent handoff plans, and searchable source memory.</p>
    <p>Vault: <code>{html_escape(str(vault_path))}</code> · Root: <code>{html_escape(root)}</code></p>

    <div class="stats">
      <div class="stat"><strong>{html_escape(str(counts.get('total', 0)))}</strong><span>Total Drops</span></div>
      <div class="stat"><strong>{html_escape(str(counts.get('drift', 0)))}</strong><span>Drift</span></div>
      <div class="stat"><strong>{html_escape(str(counts.get('reef', 0)))}</strong><span>Reef</span></div>
      <div class="stat"><strong>{html_escape(str(counts.get('pearls', 0)))}</strong><span>Pearls</span></div>
      <div class="stat"><strong>{html_escape(str(counts.get('discarded', 0)))}</strong><span>Discarded</span></div>
    </div>

    <div class="grid">
      <section>
        <h2>The mess</h2>
        <p>MemoReef starts with the honest state of a saved-link backlog.</p>
        {html_list(mess_signals)}
      </section>
      <section>
        <h2>The value</h2>
        <p>Useful saves become a Reef with Pearls, projects, and shoals.</p>
        {html_list(value_signals)}
        <p>Real Drops in this vault include: {html_escape(', '.join(title_examples) if title_examples else 'none yet')}.</p>
        <p>Detail pages: {', '.join(detail_examples) if detail_examples else 'none yet'}.</p>
        <p>Pearl or curated examples include: {html_escape(', '.join(pearl_titles or reef_titles) if (pearl_titles or reef_titles) else 'none yet')}.</p>
      </section>
      <section>
        <h2>The handoff</h2>
        <p>Review sessions and agent artifacts turn human taste into a finish plan.</p>
        {html_list(review_lines) if review_lines else '<p>No review or agent handoff artifacts were detected yet.</p>'}
      </section>
      <section>
        <h2>The library</h2>
        <p>The same Markdown Drops can be searched locally and opened as files.</p>
        {html_list(library_lines)}
        <p>Library path: <code>{html_escape((root_path / 'Drops').as_posix())}</code></p>
      </section>
      <section class="wide">
        <h2>Why local Markdown matters</h2>
        <p>Files remain readable, private, inspectable, and agent-ready. A Drop is not trapped behind a service: it is a Markdown file with frontmatter, source URL, review state, notes, and enough context for a person or local agent to understand what it is for.</p>
      </section>
      <section class="wide">
        <h2>Open local artifacts</h2>
        {artifact_links or '<p>No linked local artifacts were detected yet.</p>'}
      </section>
    </div>
  </main>
</body>
</html>
"""


def generate_app_dashboard(vault: Path, root: str = "MemoReef") -> Path:
    vault_path = vault.expanduser().resolve()
    app_dir = vault_path / root / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    drops_dir = app_dir / "drops"
    drops_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "index.html"
    path.write_text(render_app_dashboard(dashboard_state(vault_path, root)), encoding="utf-8")
    (app_dir / "pilot.html").write_text(render_pilot_page(vault_path, root), encoding="utf-8")
    (app_dir / "library.html").write_text(render_library_page(vault_path, root), encoding="utf-8")
    (app_dir / "review.html").write_text(render_review_page(vault_path, root), encoding="utf-8")
    (app_dir / "reports.html").write_text(render_reports_page(vault_path, root), encoding="utf-8")
    (app_dir / "briefs.html").write_text(render_briefs_page(vault_path, root), encoding="utf-8")
    for drop in app_drop_items(vault_path, root):
        (drops_dir / drop_detail_filename(drop)).write_text(render_drop_detail_page(vault_path, root, drop), encoding="utf-8")
    (app_dir / "tour.html").write_text(render_tour_page(vault_path, root), encoding="utf-8")
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
    import_cmd.add_argument("--limit", type=int, default=None, help="Only import the first N bookmarks. Useful for tests.")
    add_vault_import_options(import_cmd)

    import_links_cmd = sub.add_parser("import-links", help="Import a plain text URL list into Markdown Drops.")
    import_links_cmd.add_argument("links", type=Path, help="Text file with one URL per line.")
    add_vault_import_options(import_links_cmd)

    import_csv_cmd = sub.add_parser("import-csv", help="Import CSV links into Markdown Drops.")
    import_csv_cmd.add_argument("csv", type=Path, help="CSV file with title,url,source,tags columns.")
    add_vault_import_options(import_csv_cmd)

    import_docs_cmd = sub.add_parser("import-docs", help="Import PDF, DOCX, text, image, or Markdown documents into local Markdown Drops.")
    import_docs_cmd.add_argument("documents", type=Path, nargs="+", help="Document files to import (.pdf, .docx, .txt, .md, images).")
    import_docs_cmd.add_argument("--ocr", action="store_true", help="Use local OCR for image files and scanned PDFs when tesseract/pdftoppm are installed.")
    add_vault_import_options(import_docs_cmd)

    inspect_cmd = sub.add_parser("inspect", help="Inspect a browser bookmark HTML export without writing files.")
    inspect_cmd.add_argument("bookmarks", type=Path, help="Browser bookmark export HTML file.")

    review_cmd = sub.add_parser("export-review-session", help="Export Markdown Drops to review-session JSON.")
    review_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    review_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    review_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")
    review_cmd.add_argument("--project", action="append", default=[], help="Include Drops with a matching project. Repeatable.")
    review_cmd.add_argument("--shoal", action="append", default=[], help="Include Drops with a matching shoal. Repeatable.")
    review_cmd.add_argument("--status", action="append", default=[], help="Include Drops with a matching status. Repeatable.")
    review_cmd.add_argument("--tag", action="append", default=[], help="Include Drops with a matching tag. Repeatable.")
    review_cmd.add_argument("--folder", action="append", default=[], help="Include Drops with a matching folder. Repeatable.")
    review_cmd.add_argument("--hostname", action="append", default=[], help="Include Drops with a matching hostname. Repeatable.")
    review_cmd.add_argument("--pearl-only", action="store_true", help="Include only Pearl Drops.")
    review_cmd.add_argument("--exclude-status", action="append", default=[], help="Exclude Drops with a matching status. Repeatable.")

    review_cmd.add_argument("--limit", type=int, default=None, help="Cap exported Drops after sorting and filtering.")

    search_cmd = sub.add_parser("search-library", help="Search local Markdown Drops and write JSON results.")
    search_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    search_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    search_cmd.add_argument("--query", required=True, help="Search query text.")
    search_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")
    search_cmd.add_argument("--limit", type=int, default=20, help="Maximum number of matches. Default: 20")
    search_cmd.add_argument("--project", action="append", default=[], help="Search Drops with a matching project. Repeatable.")
    search_cmd.add_argument("--shoal", action="append", default=[], help="Search Drops with a matching shoal. Repeatable.")
    search_cmd.add_argument("--status", action="append", default=[], help="Search Drops with a matching status. Repeatable.")
    search_cmd.add_argument("--tag", action="append", default=[], help="Search Drops with a matching tag. Repeatable.")
    search_cmd.add_argument("--folder", action="append", default=[], help="Search Drops with a matching folder. Repeatable.")
    search_cmd.add_argument("--hostname", action="append", default=[], help="Search Drops with a matching hostname. Repeatable.")
    search_cmd.add_argument("--pearl-only", action="store_true", help="Search only Pearl Drops.")
    search_cmd.add_argument("--exclude-status", action="append", default=[], help="Exclude Drops with a matching status. Repeatable.")

    brief_cmd = sub.add_parser("brief", help="Export selected Markdown Drops into a project brief.")
    brief_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    brief_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    brief_cmd.add_argument("--output", type=Path, default=None, help="Output Markdown path. Defaults inside the vault.")
    brief_cmd.add_argument("--project", action="append", default=[], help="Include Drops with a matching project. Repeatable.")
    brief_cmd.add_argument("--shoal", action="append", default=[], help="Include Drops with a matching shoal. Repeatable.")
    brief_cmd.add_argument("--status", action="append", default=[], help="Include Drops with a matching status. Repeatable.")
    brief_cmd.add_argument("--tag", action="append", default=[], help="Include Drops with a matching tag. Repeatable.")
    brief_cmd.add_argument("--hostname", action="append", default=[], help="Include Drops with a matching hostname. Repeatable.")
    brief_cmd.add_argument("--pearl-only", action="store_true", help="Include only Pearl Drops.")
    brief_cmd.add_argument("--limit", type=int, default=None, help="Cap exported sources after sorting and filtering.")

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

    proposals_cmd = sub.add_parser("draft-agent-proposals", help="Draft proposals from an agent finish plan.")
    proposals_cmd.add_argument("--plan", type=Path, required=True, help="Agent finish plan JSON.")
    proposals_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults next to the plan.")

    apply_proposals_cmd = sub.add_parser("apply-agent-proposals", help="Apply accepted agent proposal JSON to Markdown Drops.")
    apply_proposals_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    apply_proposals_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    apply_proposals_cmd.add_argument("--proposals", type=Path, required=True, help="Agent proposals JSON from draft-agent-proposals.")
    apply_proposals_cmd.add_argument("--dry-run", action="store_true", help="Preview updates without modifying Markdown files.")
    apply_proposals_cmd.add_argument("--include-needs-review", action="store_true", help="Also apply proposals marked requires_user_review.")

    duplicate_cmd = sub.add_parser("duplicate-report", help="Create a local duplicate report for Markdown Drops.")
    duplicate_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    duplicate_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    duplicate_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")

    pilot_cmd = sub.add_parser("pilot", help="Run an offline guided local pilot setup.")
    pilot_source = pilot_cmd.add_mutually_exclusive_group(required=True)
    pilot_source.add_argument("--bookmarks", type=Path, help="Browser bookmark export HTML file.")
    pilot_source.add_argument("--links", type=Path, help="Text file with one URL per line.")
    pilot_source.add_argument("--csv", type=Path, help="CSV file with title,url,source,tags columns.")
    pilot_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    pilot_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    pilot_cmd.add_argument("--allow-duplicates", action="store_true", help="Write duplicate URLs instead of skipping them.")
    pilot_cmd.add_argument("--review-limit", type=int, default=25, help="Maximum Drops in the pilot review session. Default: 25")
    pilot_cmd.add_argument("--skip-reports", action="store_true", help="Skip local report generation.")

    pilot_check_cmd = sub.add_parser("pilot-check", help="Check whether a vault has pilot-ready local artifacts.")
    pilot_check_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    pilot_check_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")

    check_links_cmd = sub.add_parser("check-links", help="Create a local link check report for Markdown Drops.")
    check_links_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    check_links_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    check_links_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")
    check_links_cmd.add_argument("--timeout", type=float, default=5, help="HTTP timeout in seconds. Default: 5")
    check_links_cmd.add_argument("--limit", type=int, default=None, help="Check only the first N Drops.")
    check_links_cmd.add_argument("--method", choices=["head", "get", "auto"], default="auto", help="HTTP method strategy. Default: auto")

    refresh_cmd = sub.add_parser("refresh-metadata", help="Fetch saved URLs directly and refresh Drop metadata fields.")
    refresh_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    refresh_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    refresh_cmd.add_argument("--dry-run", action="store_true", help="Preview metadata updates without modifying Markdown files.")
    refresh_cmd.add_argument("--limit", type=int, default=None, help="Refresh only the first N Drops.")
    refresh_cmd.add_argument("--timeout", type=float, default=5, help="HTTP timeout in seconds. Default: 5")

    tag_reviewed_cmd = sub.add_parser("tag-reviewed", help="Add local agent-suggested tags to kept and Pearl Drops.")
    tag_reviewed_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    tag_reviewed_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    tag_reviewed_cmd.add_argument("--dry-run", action="store_true", help="Preview tags without modifying Markdown files.")
    tag_reviewed_cmd.add_argument("--limit", type=int, default=None, help="Tag only the first N Drops scanned.")

    hub_map_cmd = sub.add_parser("hub-map", help="Create Obsidian hub map notes and Drop graph links.")
    hub_map_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    hub_map_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    hub_map_cmd.add_argument("--dry-run", action="store_true", help="Preview hub notes and Drop links without modifying Markdown files.")
    hub_map_cmd.add_argument("--min-drops", type=int, default=2, help="Minimum reviewed Drops required for a hub. Default: 2")
    hub_map_cmd.add_argument("--max-hubs", type=int, default=100, help="Maximum hubs to generate. Default: 100")
    hub_map_cmd.add_argument("--output-dir", type=Path, default=None, help="Output directory for map notes. Defaults to <vault>/MemoReef/Maps")

    gardens_cmd = sub.add_parser("suggest-gardens", help="Create local project and shoal suggestion report.")
    gardens_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    gardens_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    gardens_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults inside the vault.")

    apply_gardens_cmd = sub.add_parser("apply-garden-suggestions", help="Apply accepted garden suggestions to Drop frontmatter.")
    apply_gardens_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    apply_gardens_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    apply_gardens_cmd.add_argument("--suggestions", type=Path, required=True, help="Garden suggestions JSON from suggest-gardens.")
    apply_gardens_cmd.add_argument("--accept-all", action="store_true", help="Apply all suggested project and shoal labels.")
    apply_gardens_cmd.add_argument("--accept-project", action="append", default=[], help="Apply a matching suggested project label. Repeatable.")
    apply_gardens_cmd.add_argument("--accept-shoal", action="append", default=[], help="Apply a matching suggested shoal label. Repeatable.")
    apply_gardens_cmd.add_argument("--dry-run", action="store_true", help="Preview accepted labels without modifying Markdown files.")

    app_cmd = sub.add_parser("app", help="Generate a static MemoReef local app dashboard.")
    app_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    app_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")

    serve_cmd = sub.add_parser("serve", help="Serve local Review Mode and write decisions directly to the vault.")
    serve_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    serve_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    serve_cmd.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    serve_cmd.add_argument("--lan", "--mobile", action="store_true", help="Bind to 0.0.0.0 for phone access on trusted LAN/Tailscale.")
    serve_cmd.add_argument("--port", type=int, default=8765, help="Bind port. Default: 8765")
    serve_cmd.add_argument("--limit", type=int, default=50, help="Maximum Drift Drops to load into Review Mode. Default: 50")

    phone_cmd = sub.add_parser("phone", help="Serve Review Mode for this computer's vault and print phone/QR access details.")
    phone_cmd.add_argument("--vault", type=Path, required=True, help="Path to this computer's Obsidian vault/root folder.")
    phone_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    phone_cmd.add_argument("--port", type=int, default=8765, help="Bind port. Default: 8765")
    phone_cmd.add_argument("--limit", type=int, default=50, help="Maximum Drift Drops to load into Review Mode. Default: 50")
    phone_cmd.add_argument("--qr", type=Path, default=None, help="Optional QR PNG output path. Defaults to <vault>/MemoReef/phone-triage-qr.png when qrcode is installed.")
    phone_cmd.add_argument("--no-qr", action="store_true", help="Do not try to generate a QR PNG.")

    demo_cmd = sub.add_parser("demo", help="Create a complete local MemoReef demo vault.")
    demo_cmd.add_argument("--output", type=Path, required=True, help="Directory where the demo vault should be created.")
    demo_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the demo vault. Default: MemoReef")

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

    if args.command == "import-docs":
        try:
            bookmarks, warnings = parse_documents(args.documents, ocr=args.ocr)
        except (FileNotFoundError, ValueError) as error:
            print(str(error))
            return 1
        written = write_bookmarks_to_vault(bookmarks, args.vault, args.root, allow_duplicates=args.allow_duplicates)
        source = args.documents[0] if len(args.documents) == 1 else Path(f"{len(args.documents)} documents")
        write_import_log(
            args.vault,
            args.root,
            source,
            {
                "vault": args.vault.expanduser().resolve(),
                "root": args.root,
                "documents": len(args.documents),
                "allow_duplicates": args.allow_duplicates,
            },
            len(bookmarks),
            len(written),
            0 if args.allow_duplicates else len(bookmarks) - len(written),
            warnings,
        )
        print(f"Imported {len(written)} document Drops into {Path(args.vault).expanduser().resolve() / args.root}")
        if written:
            print(f"First Drop: {written[0]}")
        if warnings:
            print(f"Warnings: {len(warnings)}")
            for warning in warnings:
                print(f"- {warning}")
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
        filters = default_review_filters(
            project=args.project,
            shoal=args.shoal,
            status=args.status,
            tag=args.tag,
            folder=args.folder,
            hostname=args.hostname,
            pearl_only=args.pearl_only,
            exclude_status=args.exclude_status,
            limit=args.limit,
        )
        output, payload = export_review_session(args.vault, args.root, args.output, filters)

        stats = payload.get("stats", {})
        drops_count = stats.get("total", 0) if isinstance(stats, dict) else 0
        print("Exported review session:")
        print(f"- drops: {drops_count}")
        print(f"- output: {output}")
        print(f"- filters: {review_filter_summary(filters)}")
        return 0

    if args.command == "search-library":
        filters = default_review_filters(
            project=args.project,
            shoal=args.shoal,
            status=args.status,
            tag=args.tag,
            folder=args.folder,
            hostname=args.hostname,
            pearl_only=args.pearl_only,
            exclude_status=args.exclude_status,
            limit=args.limit,
        )
        output, payload = search_library(args.vault, args.query, args.root, args.output, filters)
        summary = payload.get("summary", {})
        matches = summary.get("matches", 0) if isinstance(summary, dict) else 0
        print("Search library:")
        print(f"- query: {args.query}")
        print(f"- matches: {matches}")
        print(f"- output: {output}")
        print(f"- filters: {search_filter_summary(filters)}")
        return 0

    if args.command == "brief":
        filters = default_review_filters(
            project=args.project,
            shoal=args.shoal,
            status=args.status,
            tag=args.tag,
            hostname=args.hostname,
            pearl_only=args.pearl_only,
            limit=args.limit,
        )
        output, payload = create_project_brief(args.vault, args.root, args.output, filters)
        summary = payload.get("summary", {})
        sources = summary.get("sources", 0) if isinstance(summary, dict) else 0
        print("Exported project brief:")
        print(f"- sources: {sources}")
        print(f"- output: {output}")
        print(f"- filters: {review_filter_summary(filters)}")
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

    if args.command == "draft-agent-proposals":
        output, proposals, warnings = draft_agent_proposals(args.plan, args.output)
        summary = proposals.get("summary", {})
        proposed = summary.get("proposed", 0) if isinstance(summary, dict) else 0
        needs_review = summary.get("needs_review", 0) if isinstance(summary, dict) else 0
        print("Drafted agent proposals:")
        print(f"- proposed: {proposed}")
        print(f"- needs review: {needs_review}")
        print(f"- warnings: {len(warnings)}")
        print(f"- output: {output}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "apply-agent-proposals":
        updated, skipped, warnings = apply_agent_proposals(
            args.vault,
            args.proposals,
            args.root,
            args.dry_run,
            args.include_needs_review,
        )
        if args.dry_run:
            print("Dry run agent proposals:")
            print(f"- would update: {updated}")
        else:
            print("Applied agent proposals:")
            print(f"- updated: {updated}")
        print(f"- skipped: {skipped}")
        print(f"- warnings: {len(warnings)}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "duplicate-report":
        output, report = create_duplicate_report(args.vault, args.root, args.output)
        summary = report["summary"]
        assert isinstance(summary, dict)
        warnings = report.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
        print("Created duplicate report:")
        print(f"- total drops: {summary['total_drops']}")
        print(f"- exact URL groups: {summary['exact_url_groups']}")
        print(f"- same domain groups: {summary['same_domain_groups']}")
        print(f"- similar title groups: {summary['similar_title_groups']}")
        print(f"- affected drops: {summary['affected_drops']}")
        print(f"- warnings: {len(warnings)}")
        print(f"- output: {output}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "pilot":
        if args.review_limit < 0:
            print("--review-limit must be 0 or greater.")
            return 1
        if args.bookmarks is not None:
            source_kind = "bookmarks"
            source_path = args.bookmarks
        elif args.links is not None:
            source_kind = "links"
            source_path = args.links
        else:
            source_kind = "csv"
            source_path = args.csv
        summary = run_pilot(
            args.vault,
            args.root,
            source_kind,
            source_path,
            args.allow_duplicates,
            args.review_limit,
            args.skip_reports,
        )
        duplicate_report = summary.get("duplicate_report")
        print("Created MemoReef pilot vault:")
        print(f"- vault: {Path(args.vault).expanduser().resolve()}")
        print(f"- imported drops: {summary['written_count']}")
        print(f"- review session: {summary['review_session']}")
        if duplicate_report:
            print(f"- duplicate report: {duplicate_report}")
        else:
            print("- duplicate report: skipped")
        print(f"- pilot README: {summary['pilot_readme']}")
        print(f"- open pilot page: {summary['app_pilot']}")
        print(f"- open tour: {summary['app_tour']}")
        print(f"- Review Mode: {repo_root() / 'site' / 'swipe.html'}")
        return 0

    if args.command == "pilot-check":
        ok, messages = pilot_check(args.vault, args.root)
        print("MemoReef pilot check:")
        for message in messages:
            print(f"- {message}")
        return 0 if ok else 1

    if args.command == "check-links":
        output, report = create_link_check_report(
            args.vault,
            args.root,
            args.output,
            args.timeout,
            args.limit,
            args.method,
        )
        summary = report["summary"]
        assert isinstance(summary, dict)
        warnings = report.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
        print("Created link check report:")
        print(f"- total drops: {summary['total_drops']}")
        print(f"- checked: {summary['checked']}")
        print(f"- ok: {summary['ok']}")
        print(f"- broken: {summary['broken']}")
        print(f"- suspicious: {summary['suspicious']}")
        print(f"- unknown: {summary['unknown']}")
        print(f"- skipped: {summary['skipped']}")
        print(f"- warnings: {len(warnings)}")
        print(f"- output: {output}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "refresh-metadata":
        updated, skipped, warnings, planned = refresh_metadata(
            args.vault,
            args.root,
            args.dry_run,
            args.limit,
            args.timeout,
        )
        if args.dry_run:
            print("Dry run metadata refresh:")
            print(f"- would update: {updated}")
        else:
            print("Refreshed metadata:")
            print(f"- updated: {updated}")
        print(f"- skipped: {skipped}")
        print(f"- warnings: {len(warnings)}")
        if args.dry_run and planned:
            print("- would update files:")
            for item in planned:
                print(f"  - {item}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "tag-reviewed":
        result = tag_reviewed_drops(args.vault, args.root, args.dry_run, args.limit)
        if args.dry_run:
            print("Dry run reviewed Drop tagging:")
            print(f"- files that would update: {result['updated']}")
        else:
            print("Tagged reviewed Drops:")
            print(f"- files updated: {result['updated']}")
        print(f"- files scanned: {result['considered']}")
        print(f"- kept/Pearl eligible: {result['eligible']}")
        print(f"- tags added: {result['tags_added']}")
        warnings = result.get("warnings", [])
        print(f"- warnings: {len(warnings) if isinstance(warnings, list) else 0}")
        items = result.get("items", [])
        if isinstance(items, list):
            for item in items[:10]:
                if not isinstance(item, dict):
                    continue
                added_tags = item.get("added_tags", [])
                if isinstance(added_tags, list) and added_tags:
                    print(f"  - {item.get('path')}: {', '.join(str(tag) for tag in added_tags)}")
        if isinstance(warnings, list):
            for warning in warnings:
                print(f"  - {warning}")
        return 0

    if args.command == "hub-map":
        try:
            result = create_hub_map(
                args.vault,
                args.root,
                args.dry_run,
                args.min_drops,
                args.max_hubs,
                args.output_dir,
            )
        except ValueError as error:
            print(str(error))
            return 1
        hubs = result.get("hubs", [])
        drop_updates = result.get("drop_updates", [])
        files = result.get("files_that_would_change", [])
        if args.dry_run:
            print("Dry run hub map:")
            print(f"- files that would change: {len(files) if isinstance(files, list) else 0}")
        else:
            print("Created hub map:")
            changed_files = result.get("changed_files", [])
            print(f"- files changed: {len(changed_files) if isinstance(changed_files, list) else 0}")
        print(f"- reviewed Drops scanned: {result['reviewed_drops']}")
        print(f"- selected hubs: {len(hubs) if isinstance(hubs, list) else 0}")
        print(f"- Drop connection updates: {len(drop_updates) if isinstance(drop_updates, list) else 0}")
        print(f"- index: {result['index']}")
        if isinstance(hubs, list) and hubs:
            print("- candidate hubs:")
            for hub in hubs[:10]:
                if not isinstance(hub, dict):
                    continue
                print(f"  - {hub.get('label')}: {len(hub.get('drops', []))} Drops")
        if isinstance(drop_updates, list) and drop_updates:
            print("- linked Drops:")
            for path in drop_updates[:20]:
                print(f"  - {path}")
        if args.dry_run and isinstance(files, list) and files:
            print("- files:")
            for path in files[:20]:
                print(f"  - {path}")
        return 0

    if args.command == "suggest-gardens":
        output, report = create_garden_suggestions_report(args.vault, args.root, args.output)
        summary = report["summary"]
        assert isinstance(summary, dict)
        warnings = report.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
        print("Created garden suggestions:")
        print(f"- total drops: {summary['total_drops']}")
        print(f"- example drops: {summary['example_drops']}")
        print(f"- candidate drops: {summary['candidate_drops']}")
        print(f"- suggestions: {summary['suggestions']}")
        print(f"- warnings: {len(warnings)}")
        print(f"- output: {output}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "apply-garden-suggestions":
        if not args.accept_all and not args.accept_project and not args.accept_shoal:
            print("No garden suggestion accept option provided. Use --accept-all, --accept-project, or --accept-shoal.")
            return 1
        files_considered, files_updated, projects_added, shoals_added, warnings = apply_garden_suggestions(
            args.vault,
            args.suggestions,
            args.root,
            args.accept_all,
            args.accept_project,
            args.accept_shoal,
            args.dry_run,
        )
        if args.dry_run:
            print("Dry run garden suggestions:")
            print(f"- files considered: {files_considered}")
            print(f"- files that would update: {files_updated}")
            print(f"- projects that would be added: {projects_added}")
            print(f"- shoals that would be added: {shoals_added}")
        else:
            print("Applied garden suggestions:")
            print(f"- files considered: {files_considered}")
            print(f"- files updated: {files_updated}")
            print(f"- projects added: {projects_added}")
            print(f"- shoals added: {shoals_added}")
        print(f"- warnings: {len(warnings)}")
        for warning in warnings:
            print(f"  - {warning}")
        return 0

    if args.command == "app":
        output = generate_app_dashboard(args.vault, args.root)
        print(f"Generated MemoReef app dashboard: {output}")
        return 0

    if args.command == "serve":
        from .server import serve

        host = "0.0.0.0" if args.lan else args.host
        serve(args.vault, args.root, host, args.port, args.limit)
        return 0

    if args.command == "phone":
        import importlib

        server_module = importlib.import_module("memoreef.server")
        host = "0.0.0.0"
        urls = server_module.review_mode_urls(host, args.port)
        phone_urls = [url for url in urls if not url.startswith("http://localhost") and "0.0.0.0" not in url]
        primary_url = phone_urls[0] if phone_urls else urls[0]
        vault_root = args.vault.expanduser().resolve() / args.root
        url_file = vault_root / "phone-triage-url.txt"
        url_file.parent.mkdir(parents=True, exist_ok=True)
        url_file.write_text(primary_url + "\n", encoding="utf-8")

        print("MemoReef phone triage for this computer")
        print(f"- vault: {args.vault.expanduser().resolve()}")
        print("- use only on a trusted LAN/Tailscale network")
        print("- keep this command running while reviewing on the phone")
        print("Phone URLs:")
        for url in urls:
            print(f"- {url}")
        print(f"Saved phone URL: {url_file}")

        if not args.no_qr:
            qr_path = args.qr or (vault_root / "phone-triage-qr.png")
            qr_output, qr_warning = write_optional_qr_png(primary_url, qr_path)
            if qr_output:
                print(f"Saved phone QR: {qr_output}")
            if qr_warning:
                print(f"- {qr_warning}")
                print("- Open the saved URL on your phone, or install the optional qrcode package to generate a QR PNG.")

        server_module.serve(args.vault, args.root, host, args.port, args.limit)
        return 0

    if args.command == "demo":
        summary = create_demo_vault(args.output, args.root)
        print("Created MemoReef demo vault:")
        print(f"- vault: {summary['vault']}")
        print(f"- drops: {summary['drops']}")
        print(f"- review session items: {summary['review_items']}")
        print(f"- exact duplicate groups: {summary['duplicate_groups']}")
        print(f"- garden suggestions: {summary['garden_suggestions']}")
        print(f"- search matches: {summary['search_matches']}")
        print(f"- brief sources: {summary['brief_sources']}")
        print(f"- agent proposals: {summary['agent_proposals']}")
        print(f"- dashboard: {summary['dashboard']}")
        print(f"- readme: {summary['readme']}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
