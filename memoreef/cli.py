from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html import escape as html_escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

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
        "next_action": recommended_next_action(
            total,
            drift,
            latest_review_session,
            latest_review_decisions,
            latest_agent_plan,
            latest_agent_proposals,
        ),
    }


def recommended_next_action(
    total: int,
    drift: int,
    latest_review_session: Path | None,
    latest_review_decisions: Path | None,
    latest_agent_plan: Path | None,
    latest_agent_proposals: Path | None,
) -> str:
    if total == 0:
        return "Import bookmarks, a URL list, or a CSV file to create your first Drops."
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
    :root {{ color-scheme: dark; --bg:#06141c; --panel:#0d2330; --line:rgba(255,255,255,.14); --text:#eaf8fb; --muted:#9fb8c2; --pearl:#f6edd7; --green:#67f5d3; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; background: radial-gradient(circle at top left, rgba(103,245,211,.16), transparent 26rem), var(--bg); color:var(--text); }}
    main {{ width:min(1080px, calc(100% - 32px)); margin:0 auto; padding:42px 0 56px; }}
    header {{ margin-bottom:24px; }}
    .eyebrow {{ color:var(--green); text-transform:uppercase; letter-spacing:.16em; font-size:12px; font-weight:800; }}
    h1 {{ margin:.25em 0 .1em; font-size:clamp(38px, 8vw, 78px); line-height:.9; letter-spacing:-.07em; }}
    p {{ color:var(--muted); line-height:1.55; }}
    code {{ color:var(--pearl); }}
    .grid {{ display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:12px; margin:24px 0; }}
    .stat, .card {{ border:1px solid var(--line); border-radius:24px; background:rgba(13,35,48,.78); box-shadow:0 18px 60px rgba(0,0,0,.24); }}
    .stat {{ padding:18px; }}
    .stat strong {{ display:block; font-size:34px; letter-spacing:-.05em; }}
    .stat span {{ color:var(--muted); font-size:13px; }}
    .sections {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
    .card {{ padding:22px; }}
    .card h2 {{ margin:0 0 10px; font-size:22px; letter-spacing:-.04em; }}
    .next {{ border-color:rgba(103,245,211,.35); }}
    dl {{ margin:0; display:grid; gap:10px; }}
    dt {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.12em; }}
    dd {{ margin:0 0 8px; overflow-wrap:anywhere; }}
    .workflow ol {{ margin:0; padding-left:20px; color:var(--muted); }}
    .workflow li {{ margin:8px 0; }}
    @media (max-width:760px) {{ .grid, .sections {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
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
        <h2>Latest local artifacts</h2>
        <dl>
          <dt>Review session JSON</dt><dd>{html_escape(latest_review_session)}</dd>
          <dt>Review decisions JSON</dt><dd>{html_escape(latest_review_decisions)}</dd>
          <dt>Agent finish plan</dt><dd>{html_escape(latest_agent_plan)}</dd>
          <dt>Agent proposals</dt><dd>{html_escape(latest_agent_proposals)}</dd>
        </dl>
      </div>
      <div class=\"card workflow\">
        <h2>Workflow</h2>
        <ol>
          <li>Import links into Markdown Drops.</li>
          <li>Run <code>export-review-session</code> and open <code>site/swipe.html</code> for Review Mode.</li>
          <li>Export decisions from Review Mode, then run <code>apply-review-decisions</code>.</li>
          <li>Create an agent finish plan with <code>plan-agent-finish</code>.</li>
          <li>Draft Agent proposals with <code>draft-agent-proposals</code>.</li>
          <li>Dry run accepted Agent proposal updates with <code>apply-agent-proposals --dry-run</code>, then apply deliberately.</li>
        </ol>
      </div>
      <div class=\"card\">
        <h2>Review Mode</h2>
        <p>Open <code>site/swipe.html</code>, load the latest review session JSON, review a taste sample, then export <code>memoreef-review-decisions.json</code>.</p>
        <p>This dashboard is static HTML. No backend, no network, no subscription eel.</p>
      </div>
    </section>
  </main>
</body>
</html>
"""


def generate_app_dashboard(vault: Path, root: str = "MemoReef") -> Path:
    vault_path = vault.expanduser().resolve()
    app_dir = vault_path / root / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "index.html"
    path.write_text(render_app_dashboard(dashboard_state(vault_path, root)), encoding="utf-8")
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

    proposals_cmd = sub.add_parser("draft-agent-proposals", help="Draft proposals from an agent finish plan.")
    proposals_cmd.add_argument("--plan", type=Path, required=True, help="Agent finish plan JSON.")
    proposals_cmd.add_argument("--output", type=Path, default=None, help="Output JSON path. Defaults next to the plan.")

    apply_proposals_cmd = sub.add_parser("apply-agent-proposals", help="Apply accepted agent proposal JSON to Markdown Drops.")
    apply_proposals_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    apply_proposals_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")
    apply_proposals_cmd.add_argument("--proposals", type=Path, required=True, help="Agent proposals JSON from draft-agent-proposals.")
    apply_proposals_cmd.add_argument("--dry-run", action="store_true", help="Preview updates without modifying Markdown files.")
    apply_proposals_cmd.add_argument("--include-needs-review", action="store_true", help="Also apply proposals marked requires_user_review.")

    app_cmd = sub.add_parser("app", help="Generate a static MemoReef local app dashboard.")
    app_cmd.add_argument("--vault", type=Path, required=True, help="Path to the Obsidian vault/root folder.")
    app_cmd.add_argument("--root", default="MemoReef", help="Folder name inside the vault. Default: MemoReef")

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

    if args.command == "app":
        output = generate_app_dashboard(args.vault, args.root)
        print(f"Generated MemoReef app dashboard: {output}")
        return 0

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
