from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import socket
import tempfile
from urllib.parse import parse_qs, urlparse
from email.parser import BytesParser
from email.policy import default as email_policy

from .auth import bearer_token_from_header
from .bookmarks import Bookmark, write_bookmarks_to_vault
from .capture import capture_text_to_bookmarks
from .cli import apply_review_decision_payload, build_review_session_payload, default_review_filters, tag_reviewed_drops
from .documents import parse_documents


SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace("\x00", "")
    if not name:
        return "uploaded-document"
    return "".join(char if char.isalnum() or char in {".", "-", "_", " "} else "-" for char in name).strip() or "uploaded-document"


def unique_upload_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem or "uploaded-document"
    suffix = candidate.suffix
    index = 2
    while True:
        next_candidate = directory / f"{stem}-{index}{suffix}"
        if not next_candidate.exists():
            return next_candidate
        index += 1


def multipart_value_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return b""


class MemoReefHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        vault: Path,
        root: str,
        limit: int,
        capture_token: str | None = None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.vault = vault.expanduser().resolve()
        self.root = root
        self.limit = limit
        self.capture_token = capture_token


class MemoReefRequestHandler(BaseHTTPRequestHandler):
    server: MemoReefHTTPServer
    cors_api_paths = {"/api/drop", "/api/capture"}

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/swipe.html"):
            self.send_static_file(SITE_DIR / "swipe.html", "text/html; charset=utf-8")
            return
        if parsed.path.startswith("/img/"):
            self.send_static_file(SITE_DIR / parsed.path.lstrip("/"), self.content_type_for_path(parsed.path))
            return
        if parsed.path == "/api/status":
            self.send_json(
                {
                    "ok": True,
                    "vault": str(self.server.vault),
                    "root": self.server.root,
                    "message": "Connected to local MemoReef vault",
                }
            )
            return
        if parsed.path == "/api/review-session":
            self.handle_review_session(parse_qs(parsed.query))
            return
        self.send_error_json(404, "Not found")

    def do_OPTIONS(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in self.cors_api_paths:
            self.send_response(204)
            self.send_cors_headers()
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_error_json(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/review-decisions":
            self.handle_review_decisions()
            return
        if parsed.path == "/api/tag-reviewed":
            self.handle_tag_reviewed()
            return
        if parsed.path == "/api/drop":
            if not self.require_capture_auth():
                return
            self.handle_drop()
            return
        if parsed.path == "/api/capture":
            if not self.require_capture_auth():
                return
            self.handle_capture()
            return
        if parsed.path == "/api/import-docs":
            self.handle_import_docs()
            return
        self.send_error_json(404, "Not found")

    def handle_capture(self) -> None:
        payload = self.read_json_object_body()
        if payload is None:
            return

        text = str(payload.get("text") or payload.get("message") or "").strip()
        if not text:
            self.send_error_json(400, "text is required")
            return
        channel = str(payload.get("channel") or "gateway").strip() or "gateway"
        sender = str(payload.get("sender") or "").strip() or None
        title = str(payload.get("title") or "").strip() or None
        bookmarks = capture_text_to_bookmarks(text, channel=channel, sender=sender, title=title)
        if not bookmarks:
            self.send_error_json(400, "capture text must include at least one http(s) URL")
            return
        written = write_bookmarks_to_vault(bookmarks, self.server.vault, self.server.root, allow_duplicates=True)
        self.send_json({"ok": True, "captured": len(written), "written": [str(path) for path in written]})

    def require_capture_auth(self) -> bool:
        token = self.server.capture_token
        if not token:
            return True
        supplied = bearer_token_from_header(self.headers.get("Authorization"))
        if supplied and supplied == token:
            return True
        self.send_error_json(401, "capture token required")
        return False

    def handle_import_docs(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error_json(400, "multipart/form-data is required")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error_json(400, "Invalid Content-Length")
            return
        if length <= 0:
            self.send_error_json(400, "Missing upload body")
            return
        if length > 80 * 1024 * 1024:
            self.send_error_json(413, "Upload too large; keep local import batches under 80 MB")
            return

        body = self.rfile.read(length)
        raw = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
            + body
        )
        message = BytesParser(policy=email_policy).parsebytes(raw)
        files: list[Path] = []
        ocr = False
        ocr_lang: str | None = None
        engine = "builtin"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            for part in message.iter_parts():
                disposition = part.get_content_disposition()
                if disposition != "form-data":
                    continue
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                value = multipart_value_bytes(part.get_payload(decode=True))
                if filename and name == "documents":
                    safe_name = safe_upload_filename(filename)
                    target = unique_upload_path(tmp_dir, safe_name)
                    target.write_bytes(value)
                    files.append(target)
                elif name == "ocr":
                    ocr = value.decode("utf-8", errors="ignore").strip().lower() in {"1", "true", "yes", "on"}
                elif name == "ocr_lang":
                    raw_lang = value.decode("utf-8", errors="ignore").strip()
                    ocr_lang = raw_lang or None
                elif name == "engine":
                    raw_engine = value.decode("utf-8", errors="ignore").strip().lower()
                    engine = raw_engine or "builtin"

            if not files:
                self.send_error_json(400, "No documents uploaded")
                return
            try:
                bookmarks, warnings = parse_documents(files, ocr=ocr, ocr_lang=ocr_lang, engine=engine)
            except (FileNotFoundError, ValueError) as error:
                self.send_error_json(400, str(error))
                return
            written = write_bookmarks_to_vault(bookmarks, self.server.vault, self.server.root, allow_duplicates=True)

        self.send_json(
            {
                "ok": True,
                "imported": len(written),
                "written": [str(path) for path in written],
                "warnings": warnings,
                "ocr": ocr,
                "ocr_lang": ocr_lang or "",
                "engine": engine,
            }
        )

    def handle_tag_reviewed(self) -> None:
        result = tag_reviewed_drops(self.server.vault, self.server.root)
        self.send_json(result)

    def handle_review_session(self, query: dict[str, list[str]]) -> None:
        limit = self.server.limit
        raw_limit = query.get("limit", [None])[0]
        if raw_limit not in (None, ""):
            try:
                limit = max(0, int(str(raw_limit)))
            except ValueError:
                self.send_error_json(400, "limit must be an integer")
                return

        filters = default_review_filters(status=["drift"], limit=limit)
        payload = build_review_session_payload(self.server.vault, self.server.root, filters)
        self.send_json(payload)

    def handle_review_decisions(self) -> None:
        payload = self.read_json_object_body()
        if payload is None:
            return

        updated, skipped, warnings = apply_review_decision_payload(self.server.vault, payload, self.server.root)
        status = 200 if skipped == 0 else 207
        self.send_json({"ok": skipped == 0, "updated": updated, "skipped": skipped, "warnings": warnings}, status=status)

    def handle_drop(self) -> None:
        payload = self.read_json_object_body()
        if payload is None:
            return

        url = str(payload.get("url") or "").strip()
        if not url:
            self.send_error_json(400, "url is required")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            self.send_error_json(400, "url must start with http:// or https://")
            return

        title = str(payload.get("title") or "").strip() or url
        selection = str(payload.get("selection") or "").replace("\r\n", "\n").replace("\r", "\n").strip()[:4000]
        bookmark = Bookmark(title=title, url=url, clipped_selection=selection or None, clip_type="highlight" if selection else None)
        written = write_bookmarks_to_vault([bookmark], self.server.vault, self.server.root, allow_duplicates=True)
        self.send_json({"ok": True, "clipped": bool(selection), "written": [str(path) for path in written]})

    def read_json_object_body(self) -> dict[str, object] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error_json(400, "Invalid Content-Length")
            return None
        if length <= 0:
            self.send_error_json(400, "Missing JSON body")
            return None

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_error_json(400, f"Invalid JSON: {error}")
            return None
        if not isinstance(payload, dict):
            self.send_error_json(400, "JSON body must be an object")
            return None
        return payload

    def send_static_file(self, path: Path, content_type: str) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(SITE_DIR.resolve())
        except ValueError:
            self.send_error_json(403, "Forbidden")
            return
        if not resolved.exists() or not resolved.is_file():
            self.send_error_json(404, "Not found")
            return

        body = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if urlparse(self.path).path in self.cors_api_paths:
            self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status=status)

    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    @staticmethod
    def content_type_for_path(path: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix == ".svg":
            return "image/svg+xml"
        if suffix == ".webp":
            return "image/webp"
        if suffix == ".png":
            return "image/png"
        if suffix == ".jpg" or suffix == ".jpeg":
            return "image/jpeg"
        if suffix == ".webm":
            return "video/webm"
        if suffix == ".mp4":
            return "video/mp4"
        return "application/octet-stream"


def is_loopback_bind(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "::1", "[::1]"}:
        return True
    try:
        return ipaddress.ip_address(normalized.strip("[]")).is_loopback
    except ValueError:
        return False


def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if not ipaddress.ip_address(address).is_loopback:
                addresses.add(address)
    except OSError:
        pass
    try:
        hostnames = {socket.gethostname(), socket.getfqdn()}
        for hostname in hostnames:
            for family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_INET):
                if family == socket.AF_INET:
                    address = sockaddr[0]
                    if not ipaddress.ip_address(address).is_loopback:
                        addresses.add(address)
    except OSError:
        return []
    return sorted(addresses)


def review_mode_urls(host: str, port: int, addresses: list[str] | None = None) -> list[str]:
    urls: list[str] = []

    def add(url: str) -> None:
        if url not in urls:
            urls.append(url)

    normalized = host.strip()
    if normalized in {"0.0.0.0", ""}:
        add(f"http://localhost:{port}/")
        for address in addresses if addresses is not None else local_ipv4_addresses():
            add(f"http://{address}:{port}/")
        add(f"http://0.0.0.0:{port}/")
    elif is_loopback_bind(normalized):
        add(f"http://localhost:{port}/")
        if normalized not in {"localhost", "::1", "[::1]"}:
            add(f"http://{normalized}:{port}/")
    else:
        add(f"http://{normalized}:{port}/")
        for address in addresses if addresses is not None else local_ipv4_addresses():
            add(f"http://{address}:{port}/")
        add(f"http://localhost:{port}/")
    return urls


def create_server(
    vault: Path,
    root: str = "MemoReef",
    host: str = "127.0.0.1",
    port: int = 8765,
    limit: int = 50,
    capture_token: str | None = None,
) -> MemoReefHTTPServer:
    return MemoReefHTTPServer((host, port), MemoReefRequestHandler, vault, root, limit, capture_token)


def serve(vault: Path, root: str = "MemoReef", host: str = "127.0.0.1", port: int = 8765, limit: int = 50, capture_token: str | None = None) -> None:
    server = create_server(vault, root, host, port, limit, capture_token)
    try:
        print("Serving MemoReef Review Mode:")
        for url in review_mode_urls(host, server.server_port):
            print(f"- {url}")
        print(f"Connected vault: {server.vault}")
        if capture_token:
            print("Capture API token protection: enabled")
            print(f"Capture token: {capture_token}")
        if not is_loopback_bind(host):
            print("WARNING: MemoReef is bound to a network-accessible host.")
            print("The local vault write API can be reached by devices on this network.")
            print("Use this only on a trusted LAN or Tailscale network, and stop the server when done.")
        print("Press Ctrl+C to stop.")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped MemoReef local server.")
    finally:
        server.server_close()
