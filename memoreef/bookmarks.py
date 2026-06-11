from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import html
import re
from typing import Iterable


@dataclass
class Bookmark:
    title: str
    url: str
    add_date: str | None = None
    icon: str | None = None
    folders: list[str] = field(default_factory=list)


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
        "status: drift",
        "agent_ready: true",
        "pearl: false",
    ]
    if bookmark.add_date:
        lines.append(f"browser_add_date: {yaml_quote(bookmark.add_date)}")
    if bookmark.folders:
        lines.append("folders:")
        for folder in bookmark.folders:
            lines.append(f"  - {yaml_quote(folder)}")
    if folder_tags:
        lines.append("tags:")
        for tag in folder_tags:
            lines.append(f"  - {tag}")
    lines.extend([
        "---",
        "",
        f"# {bookmark.title}",
        "",
        f"Source: [{bookmark.url}]({bookmark.url})",
        "",
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


def write_bookmarks_to_vault(bookmarks: Iterable[Bookmark], vault: str | Path, root: str = "MemoReef") -> list[Path]:
    base = Path(vault).expanduser().resolve() / root / "Drops"
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for bookmark in bookmarks:
        stem = slugify(bookmark.title)
        path = unique_path(base, stem)
        path.write_text(bookmark_to_markdown(bookmark), encoding="utf-8")
        written.append(path)
    return written
