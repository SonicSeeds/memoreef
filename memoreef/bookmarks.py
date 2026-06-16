from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import csv
import html
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
    pearl: bool = False
    folders: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    shoals: list[str] = field(default_factory=list)
    triaged_at: str | None = None
    clipped_selection: str | None = None


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
        "pearl": bool(frontmatter.get("pearl", False)),
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
        f"pearl: {'true' if bookmark.pearl else 'false'}",
    ]
    if bookmark.add_date:
        lines.append(f"browser_add_date: {yaml_quote(bookmark.add_date)}")
    if bookmark.source:
        lines.append(f"import_source: {yaml_quote(bookmark.source)}")
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
