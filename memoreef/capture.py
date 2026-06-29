from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from .bookmarks import Bookmark, clean_text, slugify


URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)
CAPTURE_COMMANDS = {"reef", "drop", "signal", "youtube", "yt", "x", "twitter"}
TRAILING_URL_PUNCTUATION = ".,;:!?)]}”’"


@dataclass(frozen=True)
class CaptureIntent:
    command: str
    raw_text: str
    body: str
    urls: list[str]
    note: str
    channel: str
    sender: str | None = None


def normalize_capture_command(command: str) -> str:
    normalized = command.strip().lower().lstrip("/#")
    if normalized == "drop":
        return "reef"
    if normalized == "yt":
        return "youtube"
    if normalized == "twitter":
        return "x"
    return normalized if normalized in CAPTURE_COMMANDS else "reef"


def is_capture_command(command: str) -> bool:
    return command.strip().lower().lstrip("/#") in CAPTURE_COMMANDS


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_URL_PUNCTUATION)
        if url and url not in urls:
            urls.append(url)
    return urls


def parse_capture_text(text: str, channel: str = "manual", sender: str | None = None) -> CaptureIntent:
    raw_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    first_line, _, remainder = raw_text.partition("\n")
    command = "reef"
    body = raw_text

    command_match = re.match(r"^\s*(?:[/#])?([A-Za-z][A-Za-z0-9_-]{0,31})\s*:\s*(.*)$", first_line)
    if command_match and is_capture_command(command_match.group(1)):
        command = normalize_capture_command(command_match.group(1))
        body = "\n".join(part for part in [command_match.group(2), remainder] if part).strip()
    else:
        slash_match = re.match(r"^\s*(?:[/#])([A-Za-z][A-Za-z0-9_-]{0,31})\s+(.*)$", first_line)
        if slash_match and is_capture_command(slash_match.group(1)):
            command = normalize_capture_command(slash_match.group(1))
            body = "\n".join(part for part in [slash_match.group(2), remainder] if part).strip()

    urls = extract_urls(body)
    note = body
    for url in urls:
        note = note.replace(url, " ")
    note = clean_text(note)
    return CaptureIntent(command=command, raw_text=raw_text, body=body, urls=urls, note=note, channel=clean_text(channel) or "manual", sender=clean_text(sender or "") or None)


def capture_title_for_url(url: str, intent: CaptureIntent, provided_title: str | None = None) -> str:
    title = clean_text(provided_title or "")
    if title:
        return title
    if intent.note:
        return intent.note[:120]
    host = urlsplit(url).netloc.replace("www.", "")
    if host:
        if intent.command == "youtube":
            return f"YouTube capture from {host}"
        if intent.command == "x":
            return f"X capture from {host}"
        if intent.command == "signal":
            return f"Signal from {host}"
    return url


def capture_tags(intent: CaptureIntent, url: str) -> list[str]:
    tags = ["capture", f"capture-{slugify(intent.channel, 32)}"]
    if intent.command not in {"reef"}:
        tags.append(intent.command)
    host = urlsplit(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        tags.append("youtube")
    if "x.com" in host or "twitter.com" in host:
        tags.append("x")
    deduped: list[str] = []
    for tag in tags:
        if tag and tag not in deduped:
            deduped.append(tag)
    return deduped


def capture_folder(intent: CaptureIntent) -> str:
    if intent.command == "signal":
        return "Signals"
    if intent.command == "youtube":
        return "YouTube"
    if intent.command == "x":
        return "X"
    return "Inbox"


def render_capture_document_text(intent: CaptureIntent) -> str:
    lines = [
        "### Capture message",
        "",
        intent.raw_text or "_No message text captured._",
        "",
        "### Capture metadata",
        "",
        f"- Channel: {intent.channel}",
        f"- Command: {intent.command}",
    ]
    if intent.sender:
        lines.append(f"- Sender: {intent.sender}")
    return "\n".join(lines).strip()


def capture_text_to_bookmarks(text: str, channel: str = "manual", sender: str | None = None, title: str | None = None) -> list[Bookmark]:
    intent = parse_capture_text(text, channel=channel, sender=sender)
    document_text = render_capture_document_text(intent)
    bookmarks: list[Bookmark] = []
    for url in intent.urls:
        bookmarks.append(
            Bookmark(
                title=capture_title_for_url(url, intent, provided_title=title if len(intent.urls) == 1 else None),
                url=url,
                source=f"channel-{intent.channel}",
                folders=[capture_folder(intent), intent.channel],
                tags=capture_tags(intent, url),
                document_text=document_text,
                document_type="channel-capture",
                document_extraction_engine="memoreef-capture",
            )
        )
    return bookmarks
