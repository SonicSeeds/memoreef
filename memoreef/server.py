from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import parse_qs, urlparse

from .bookmarks import Bookmark, write_bookmarks_to_vault
from .cli import apply_review_decision_payload, build_review_session_payload, default_review_filters, tag_reviewed_drops


SITE_DIR = Path(__file__).resolve().parent.parent / "site"


class MemoReefHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        vault: Path,
        root: str,
        limit: int,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.vault = vault.expanduser().resolve()
        self.root = root
        self.limit = limit


class MemoReefRequestHandler(BaseHTTPRequestHandler):
    server: MemoReefHTTPServer
    cors_api_paths = {"/api/drop"}

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
            self.handle_drop()
            return
        self.send_error_json(404, "Not found")

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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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


def create_server(vault: Path, root: str = "MemoReef", host: str = "127.0.0.1", port: int = 8765, limit: int = 50) -> MemoReefHTTPServer:
    return MemoReefHTTPServer((host, port), MemoReefRequestHandler, vault, root, limit)


def serve(vault: Path, root: str = "MemoReef", host: str = "127.0.0.1", port: int = 8765, limit: int = 50) -> None:
    server = create_server(vault, root, host, port, limit)
    try:
        print("Serving MemoReef Review Mode:")
        for url in review_mode_urls(host, server.server_port):
            print(f"- {url}")
        print(f"Connected vault: {server.vault}")
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
