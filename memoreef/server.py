from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .cli import apply_review_decision_payload, build_review_session_payload, default_review_filters


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

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/review-decisions":
            self.handle_review_decisions()
            return
        self.send_error_json(404, "Not found")

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
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error_json(400, "Invalid Content-Length")
            return
        if length <= 0:
            self.send_error_json(400, "Missing JSON body")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_error_json(400, f"Invalid JSON: {error}")
            return
        if not isinstance(payload, dict):
            self.send_error_json(400, "JSON body must be an object")
            return

        updated, skipped, warnings = apply_review_decision_payload(self.server.vault, payload, self.server.root)
        status = 200 if skipped == 0 else 207
        self.send_json({"ok": skipped == 0, "updated": updated, "skipped": skipped, "warnings": warnings}, status=status)

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
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"ok": False, "error": message}, status=status)

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


def create_server(vault: Path, root: str = "MemoReef", host: str = "127.0.0.1", port: int = 8765, limit: int = 50) -> MemoReefHTTPServer:
    return MemoReefHTTPServer((host, port), MemoReefRequestHandler, vault, root, limit)


def serve(vault: Path, root: str = "MemoReef", host: str = "127.0.0.1", port: int = 8765, limit: int = 50) -> None:
    server = create_server(vault, root, host, port, limit)
    try:
        print(f"Serving MemoReef Review Mode at http://{host}:{server.server_port}/")
        print(f"Connected vault: {server.vault}")
        print("Press Ctrl+C to stop.")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped MemoReef local server.")
    finally:
        server.server_close()
