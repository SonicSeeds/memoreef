from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import csv
import html
import json
import re
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass
class Bookmark:
    title: str
    url: str
    add_date: str | None = None
    icon: str | None = None
    source: str | None = None
    status: str = "drift"
    treasure: bool = False
    pearl: bool = False
    folders: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    shoals: list[str] = field(default_factory=list)
    triaged_at: str | None = None
    clipped_selection: str | None = None
    clip_type: str | None = None
    document_text: str | None = None
    document_visual_analysis: str | None = None
    document_type: str | None = None
    original_file: str | None = None
    document_numeric_analysis: str | None = None
    document_extraction_engine: str | None = None
    document_extraction_engine_version: str | None = None

    def __post_init__(self) -> None:
        if self.pearl:
            self.treasure = True


class BrowserBookmarkParser(HTMLParser):
    """Parse Netscape bookmark HTML exports from Chrome/Brave/Arc/Firefox/Safari-ish sources.

    Browser bookmark exports are not valid modern HTML. They are old Netscape bookmark
    files: nested <DL>/<DT>/<H3>/<A> structures. This parser keeps a folder stack and
    emits each <A> as a Bookmark.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bookmarks: list[Bookmark] = []
        self._folder_stack: list[str] = []
        self._pending_folder: dict[str, str | None] | None = None
        self._pending_link: dict[str, str | None] | None = None
        self._capture: str | None = None
        self._text: list[str] = []
        self._last_closed_folder: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): v for k, v in attrs}
        if tag == "h3":
            self._pending_folder = {"add_date": attrs_dict.get("add_date")}
            self._capture = "folder"
            self._text = []
        elif tag == "a":
            self._pending_link = {
                "href": attrs_dict.get("href"),
                "add_date": attrs_dict.get("add_date"),
                "icon": attrs_dict.get("icon"),
            }
            self._capture = "link"
            self._text = []
        elif tag == "dl":
            if self._last_closed_folder:
                self._folder_stack.append(self._last_closed_folder)
                self._last_closed_folder = None

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "h3" and self._pending_folder is not None:
            title = clean_text("".join(self._text))
            if title:
                self._last_closed_folder = title
            self._pending_folder = None
            self._capture = None
            self._text = []
        elif tag == "a" and self._pending_link is not None:
            title = clean_text("".join(self._text))
            url = self._pending_link.get("href")
            if title and url:
                self.bookmarks.append(
                    Bookmark(
                        title=title,
                        url=url,
                        add_date=self._pending_link.get("add_date"),
                        icon=self._pending_link.get("icon"),
                        folders=list(self._folder_stack),
                    )
                )
            self._pending_link = None
            self._capture = None
            self._text = []
        elif tag == "dl":
            if self._folder_stack:
                self._folder_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text.append(data)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_bookmarks_html(path: str | Path) -> list[Bookmark]:
    parser = BrowserBookmarkParser()
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    parser.feed(content)
    return parser.bookmarks


def parse_links_text(path: str | Path) -> list[Bookmark]:
    bookmarks: list[Bookmark] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        url = line.strip()
        if url:
            bookmarks.append(Bookmark(title=url, url=url))
    return bookmarks


def parse_links_csv(path: str | Path) -> list[Bookmark]:
    bookmarks: list[Bookmark] = []
    with Path(path).open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            url = clean_text(row.get("url") or "")
            if not url:
                continue
            title = clean_text(row.get("title") or "") or url
            source = clean_text(row.get("source") or "") or None
            bookmarks.append(Bookmark(title=title, url=url, source=source, tags=parse_tag_list(row.get("tags") or "")))
    return bookmarks


def parse_tokwise_jsonl(path: str | Path) -> list[Bookmark]:
    """Parse Tokwise videos.jsonl into MemoReef short-form-video Drops.

    Tokwise stores one normalized TikTok/short-form video record per line. MemoReef
    imports the local transcript/classification as source memory without calling
    TikTok or reading browser cookies.
    """
    bookmarks: list[Bookmark] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            video = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid Tokwise JSONL on line {line_number}: {error.msg}") from error
        if not isinstance(video, dict):
            raise ValueError(f"Invalid Tokwise JSONL on line {line_number}: expected an object")
        bookmark = tokwise_video_to_bookmark(video)
        if bookmark is not None:
            bookmarks.append(bookmark)
    return bookmarks


def tokwise_video_to_bookmark(video: dict[str, object]) -> Bookmark | None:
    url = clean_text(str(video.get("canonicalUrl") or video.get("url") or ""))
    if not url:
        return None

    author = video.get("author") if isinstance(video.get("author"), dict) else {}
    author_username = clean_text(str(author.get("username") or "")) if isinstance(author, dict) else ""
    description = clean_text(str(video.get("description") or ""))
    title = description or (f"TikTok by @{author_username}" if author_username else url)

    classification = video.get("classification") if isinstance(video.get("classification"), dict) else {}
    category = clean_text(str(classification.get("category") or "")) if isinstance(classification, dict) else ""
    domain = clean_text(str(classification.get("domain") or "")) if isinstance(classification, dict) else ""
    summary = clean_text(str(classification.get("summary") or "")) if isinstance(classification, dict) else ""
    topics = list_of_clean_strings(classification.get("topics") if isinstance(classification, dict) else None)
    hashtags = list_of_clean_strings(video.get("hashtags"))

    folders = ["Tokwise"]
    collection = video.get("collection") if isinstance(video.get("collection"), dict) else {}
    collection_name = clean_text(str(collection.get("name") or "")) if isinstance(collection, dict) else ""
    if collection_name:
        folders.append(collection_name)

    tags = ["short-form-video"]
    for value in [category, domain, *topics, *hashtags]:
        tag = slugify(value, 48)
        if tag and tag not in tags:
            tags.append(tag)

    transcript = video.get("transcript") if isinstance(video.get("transcript"), dict) else {}
    transcript_text = str(transcript.get("text") or "").strip() if isinstance(transcript, dict) else ""

    return Bookmark(
        title=title,
        url=url,
        add_date=clean_text(str(video.get("savedAt") or video.get("createdAt") or "")) or None,
        source="tokwise",
        folders=folders,
        tags=tags,
        document_text=render_tokwise_document_text(video, summary=summary, transcript_text=transcript_text),
        document_type="short-form-video",
        document_extraction_engine="tokwise",
    )


def render_tokwise_document_text(video: dict[str, object], summary: str, transcript_text: str) -> str:
    parts: list[str] = []
    if summary:
        parts.extend(["### Tokwise summary", "", summary, ""])

    description = str(video.get("description") or "").strip()
    if description:
        parts.extend(["### Description", "", description, ""])

    author = video.get("author") if isinstance(video.get("author"), dict) else {}
    author_username = str(author.get("username") or "").strip() if isinstance(author, dict) else ""
    if author_username:
        parts.extend(["### Author", "", f"@{author_username}", ""])

    classification = video.get("classification") if isinstance(video.get("classification"), dict) else {}
    if isinstance(classification, dict):
        category = str(classification.get("category") or "").strip()
        domain = str(classification.get("domain") or "").strip()
        topics = list_of_clean_strings(classification.get("topics"))
        if category or domain or topics:
            parts.extend(["### Tokwise classification", ""])
            if category:
                parts.append(f"- Category: {category}")
            if domain:
                parts.append(f"- Domain: {domain}")
            if topics:
                parts.append(f"- Topics: {', '.join(topics)}")
            parts.append("")

    hashtags = list_of_clean_strings(video.get("hashtags"))
    if hashtags:
        parts.extend(["### Hashtags", "", " ".join(f"#{tag}" for tag in hashtags), ""])

    stats = video.get("stats") if isinstance(video.get("stats"), dict) else {}
    if isinstance(stats, dict):
        stat_lines = []
        for label, key in [("Plays", "plays"), ("Likes", "likes"), ("Comments", "comments"), ("Shares", "shares"), ("Saves", "saves")]:
            value = stats.get(key)
            if value not in (None, ""):
                stat_lines.append(f"- {label}: {value}")
        if stat_lines:
            parts.extend(["### TikTok stats", "", *stat_lines, ""])

    parts.extend(["### Transcript", "", transcript_text or "_No transcript available in Tokwise export._"])
    return "\n".join(parts).strip()


def list_of_clean_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = clean_text(str(item))
        if text:
            items.append(text)
    return items


def parse_tag_list(value: str) -> list[str]:
    tags: list[str] = []
    for tag in re.split(r"[,;]", value):
        tag = tag.strip().lstrip("#")
        if tag:
            tags.append(tag)
    return tags


def parse_markdown_frontmatter(content: str) -> tuple[dict[str, object], str]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, content

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return {}, content

    frontmatter: dict[str, object] = {}
    frontmatter_lines = lines[1:end]
    body = "\n".join(lines[end + 1 :])
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if not line.strip() or line.startswith(" "):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            frontmatter[key] = parse_frontmatter_value(raw_value)
            i += 1
            continue

        values: list[object] = []
        i += 1
        while i < len(frontmatter_lines) and frontmatter_lines[i].startswith("  - "):
            values.append(parse_frontmatter_value(frontmatter_lines[i][4:].strip()))
            i += 1
        frontmatter[key] = values
    return frontmatter, body


def parse_frontmatter_value(value: str) -> object:
    if value == "true":
        return True
    if value == "false":
        return False
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1].replace('\\"', '"')
    return value


def extract_summary(body: str) -> str:
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != "## Summary":
            continue
        summary: list[str] = []
        for summary_line in lines[i + 1 :]:
            if summary_line.startswith("## "):
                break
            summary.append(summary_line)
        return "\n".join(summary).strip()
    return ""


def markdown_drop_to_review_item(path: Path, vault: str | Path) -> dict[str, object]:
    vault_path = Path(vault).expanduser().resolve()
    relative_path = path.resolve().relative_to(vault_path).as_posix()
    frontmatter, body = parse_markdown_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
    folders = frontmatter.get("folders", [])
    tags = frontmatter.get("tags", [])
    if not isinstance(folders, list):
        folders = []
    if not isinstance(tags, list):
        tags = []

    return {
        "id": relative_path,
        "path": relative_path,
        "title": str(frontmatter.get("title") or path.stem),
        "url": str(frontmatter.get("url") or ""),
        "status": str(frontmatter.get("status") or "drift"),
        "treasure": bool(frontmatter.get("treasure", frontmatter.get("pearl", False))),
        "folders": [str(folder) for folder in folders],
        "tags": [str(tag) for tag in tags],
        "summary": extract_summary(body),
    }


def frontmatter_value_to_yaml(value: object, quote_string: bool = True) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if quote_string:
        return yaml_quote(str(value))
    return str(value)


def markdown_frontmatter_to_text(frontmatter: dict[str, object]) -> str:
    lines = ["---"]
    unquoted_string_keys = {"type", "status"}
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {frontmatter_value_to_yaml(item)}")
        else:
            lines.append(f"{key}: {frontmatter_value_to_yaml(value, key not in unquoted_string_keys)}")
    lines.append("---")
    return "\n".join(lines)


def update_markdown_frontmatter(content: str, updates: dict[str, object]) -> str:
    frontmatter, body = parse_markdown_frontmatter(content)
    frontmatter.update(updates)
    updated = markdown_frontmatter_to_text(frontmatter)
    if body:
        return f"{updated}\n{body}"
    return f"{updated}\n"


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc
    if parsed.hostname:
        userinfo = ""
        if parsed.username:
            userinfo = parsed.username
            if parsed.password:
                userinfo += f":{parsed.password}"
            userinfo += "@"
        host = parsed.hostname.lower()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{userinfo}{host}{port}"

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not is_tracking_param(key)
    ]
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, parsed.path, query, parsed.fragment))


def is_tracking_param(name: str) -> bool:
    normalized = name.lower()
    return normalized.startswith("utm_") or normalized in {"fbclid", "gclid"}


def slugify(value: str, max_len: int = 80) -> str:
    value = value.lower().strip()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^a-z0-9äöüß]+", "-", value, flags=re.IGNORECASE)
    value = value.strip("-") or "untitled"
    return value[:max_len].strip("-") or "untitled"


def unique_path(directory: Path, stem: str, suffix: str = ".md") -> Path:
    candidate = directory / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = directory / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def yaml_quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def bookmark_to_markdown(bookmark: Bookmark) -> str:
    folder_tags = [slugify(f, 32) for f in bookmark.folders if f]
    lines = [
        "---",
        f"title: {yaml_quote(bookmark.title)}",
        f"url: {yaml_quote(bookmark.url)}",
        "type: drop",
        f"status: {bookmark.status}",
        "agent_ready: true",
        "ai_export: local_only",
        f"treasure: {'true' if bookmark.treasure else 'false'}",
    ]
    if bookmark.add_date:
        lines.append(f"browser_add_date: {yaml_quote(bookmark.add_date)}")
    if bookmark.source:
        lines.append(f"import_source: {yaml_quote(bookmark.source)}")
    if bookmark.clipped_selection:
        lines.append("has_clipped_selection: true")
        lines.append(f"clip_type: {yaml_quote(bookmark.clip_type or 'highlight')}")
    if bookmark.document_text is not None:
        lines.append("has_document_text: true")
    if bookmark.document_visual_analysis:
        lines.append("has_document_visual_analysis: true")
    if bookmark.document_numeric_analysis:
        lines.append("has_document_numeric_artifacts: true")
    if bookmark.document_type:
        lines.append(f"document_type: {yaml_quote(bookmark.document_type)}")
    if bookmark.original_file:
        lines.append(f"original_file: {yaml_quote(bookmark.original_file)}")
    if bookmark.document_extraction_engine:
        lines.append(f"document_extraction_engine: {yaml_quote(bookmark.document_extraction_engine)}")
    if bookmark.document_extraction_engine_version:
        lines.append(f"document_extraction_engine_version: {yaml_quote(bookmark.document_extraction_engine_version)}")
    if bookmark.projects:
        lines.append("projects:")
        for project in bookmark.projects:
            lines.append(f"  - {yaml_quote(project)}")
    if bookmark.shoals:
        lines.append("shoals:")
        for shoal in bookmark.shoals:
            lines.append(f"  - {yaml_quote(shoal)}")
    if bookmark.triaged_at:
        lines.append(f"triaged_at: {yaml_quote(bookmark.triaged_at)}")
    if bookmark.folders:
        lines.append("folders:")
        for folder in bookmark.folders:
            lines.append(f"  - {yaml_quote(folder)}")
    if bookmark.tags or folder_tags:
        lines.append("tags:")
        for tag in bookmark.tags:
            lines.append(f"  - {yaml_quote(tag)}")
        for tag in folder_tags:
            lines.append(f"  - {tag}")
    lines.extend([
        "---",
        "",
        f"# {bookmark.title}",
        "",
        f"Source: [{bookmark.url}]({bookmark.url})",
        "",
    ])
    if bookmark.clipped_selection:
        lines.extend([
            "## Clipped selection",
            "",
            *[f"> {line}" if line else ">" for line in bookmark.clipped_selection.splitlines()],
            "",
        ])
    if bookmark.document_text is not None:
        lines.extend([
            "## Document text",
            "",
        ])
        if bookmark.document_text.strip():
            lines.extend([bookmark.document_text.strip(), ""])
        else:
            lines.extend(["_No extractable text found._", ""])
    if bookmark.document_numeric_analysis:
        lines.extend([
            "## Numeric artifacts",
            "",
            bookmark.document_numeric_analysis.strip(),
            "",
        ])
    if bookmark.document_visual_analysis:
        lines.extend([
            "## Visual artifacts",
            "",
            bookmark.document_visual_analysis.strip(),
            "",
        ])
    lines.extend([
        "## Summary",
        "",
        "_Not enriched yet._",
        "",
        "## Notes",
        "",
        "",
        "## Agent Brief",
        "",
        "- Status: Drift",
        "- Suggested next action: triage this Drop.",
        "",
    ])
    return "\n".join(lines)


def write_bookmarks_to_vault(
    bookmarks: Iterable[Bookmark],
    vault: str | Path,
    root: str = "MemoReef",
    allow_duplicates: bool = False,
) -> list[Path]:
    base = Path(vault).expanduser().resolve() / root / "Drops"
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    seen_urls: set[str] = set()
    for bookmark in bookmarks:
        canonical_url = canonicalize_url(bookmark.url)
        if not allow_duplicates and canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        stem = slugify(bookmark.title)
        path = unique_path(base, stem)
        path.write_text(bookmark_to_markdown(bookmark), encoding="utf-8")
        written.append(path)
    return written
