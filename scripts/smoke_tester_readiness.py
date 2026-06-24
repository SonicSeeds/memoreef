#!/usr/bin/env python3
"""Smoke-test MemoReef's first-tester path.

This script is intentionally boring. It proves that a fresh checkout can create a
sample vault, import small real-source stand-ins, generate review/app artifacts,
and produce Markdown output without needing network access or API keys.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path, label: str) -> subprocess.CompletedProcess[str]:
    print(f"\n==> {label}")
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(f"FAILED: {label} exited with {result.returncode}")
    return result


def require(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"FAILED: missing {label}: {path}")
    print(f"ok: {label}: {path}")


def require_contains(path: Path, needle: str, label: str) -> None:
    require(path, label)
    text = path.read_text(encoding="utf-8")
    if needle not in text:
        raise SystemExit(f"FAILED: {label} does not contain {needle!r}: {path}")
    print(f"ok: {label} contains {needle!r}")


def newest_file(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise SystemExit(f"FAILED: no files matching {pattern!r} in {directory}")
    return matches[0]


def first_file_containing(directory: Path, pattern: str, needle: str) -> Path:
    for path in sorted(directory.glob(pattern)):
        if needle in path.read_text(encoding="utf-8", errors="replace"):
            return path
    raise SystemExit(f"FAILED: no {pattern!r} file in {directory} contains {needle!r}")


def start_local_article_server(web_root: Path) -> tuple[socketserver.TCPServer, str]:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web_root))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    return server, f"http://{host}:{port}/article.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test MemoReef's tester-readiness path.")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter to use. Defaults to this interpreter.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary smoke vault for inspection.")
    args = parser.parse_args()

    temp_root = Path(tempfile.mkdtemp(prefix="memoreef-smoke-"))
    vault = temp_root / "vault"
    links = temp_root / "links.txt"
    article_links = temp_root / "article-links.txt"
    doc = temp_root / "field-note.md"
    web_root = temp_root / "web"
    bookmarks = ROOT / "examples" / "bookmarks.html"
    server: socketserver.TCPServer | None = None

    try:
        require(bookmarks, "example bookmark export")
        web_root.mkdir()
        (web_root / "article.html").write_text(
            """<!doctype html><html><head><title>Local Article</title></head><body>
<article><h1>Local article extraction smoke</h1><p>This local article proves MemoReef can fetch readable article text from a saved URL.</p><p>The smoke test keeps this on localhost so no external network or API key is required.</p></article>
</body></html>""",
            encoding="utf-8",
        )
        server, article_url = start_local_article_server(web_root)
        links.write_text("https://example.org/research-memory\nhttps://example.org/source-truth\n", encoding="utf-8")
        article_links.write_text(f"{article_url}\n", encoding="utf-8")
        doc.write_text(
            "# Field note\n\nThis is a small local document used to verify MemoReef document import.\n",
            encoding="utf-8",
        )

        py = args.python
        cli = [py, "-m", "memoreef.cli"]

        run(cli + ["pilot", "--bookmarks", str(bookmarks), "--vault", str(vault), "--review-limit", "3"], ROOT, "create sample pilot vault")
        root = vault / "MemoReef"
        require(root / "app" / "pilot.html", "pilot page")
        require(root / "app" / "gravity.html", "Gravity Map page")
        require(root / "app" / "index.html", "local app dashboard")
        require(root / "PILOT_README.md", "pilot readme")
        drops = root / "Drops"
        require(drops, "Drops folder")
        if len(list(drops.glob("*.md"))) < 3:
            raise SystemExit("FAILED: expected at least 3 sample Drops")
        print("ok: sample Drops created")

        article_vault = temp_root / "article-vault"
        run(cli + ["import-links", str(article_links), "--vault", str(article_vault)], ROOT, "import localhost article URL")
        run(cli + ["extract-articles", "--vault", str(article_vault)], ROOT, "extract local web article")
        article_drops = article_vault / "MemoReef" / "Drops"
        article_drop = first_file_containing(article_drops, "*.md", "Local article extraction smoke")
        require_contains(article_drop, "## Article text", "article Drop")
        require_contains(article_drop, "article_extraction_status:", "article Drop")

        run(cli + ["import-links", str(links), "--vault", str(vault)], ROOT, "import URL list")
        run(cli + ["import-docs", str(doc), "--vault", str(vault)], ROOT, "import local Markdown document")
        require_contains(newest_file(drops, "field-note*.md"), "## Document text", "document Drop")

        review_dir = root / "review-sessions"
        run(cli + ["export-review-session", "--vault", str(vault), "--status", "drift", "--limit", "5"], ROOT, "export review session")
        review_session = newest_file(review_dir, "*-review-session.json")
        data = json.loads(review_session.read_text(encoding="utf-8"))
        if not data.get("items"):
            raise SystemExit("FAILED: review session has no items")
        print(f"ok: review session contains {len(data['items'])} item(s)")

        run(cli + ["dive", "research memory", "--vault", str(vault), "--limit", "3"], ROOT, "run Pearl Dive")
        answers_dir = root / "answers"
        dive_report = newest_file(answers_dir, "*-dive-report.md")
        require_contains(dive_report, "## Retrieved Pearls", "Pearl Dive report")
        require_contains(dive_report, "## Uncharted Gaps", "Pearl Dive gaps")

        run(cli + ["app", "--vault", str(vault)], ROOT, "regenerate app dashboard")
        require_contains(root / "app" / "index.html", "MemoReef", "dashboard")
        require_contains(root / "app" / "dive.html", "Pearl Dive", "Pearl Dive page")
        require_contains(root / "app" / "dive.html", "Latest Dive Report", "Pearl Dive page latest report")
        require_contains(root / "app" / "review.html", "Review Mode", "review launcher")
        require_contains(root / "app" / "library.html", "Library", "library page")

        print("\nMemoReef tester-readiness smoke: OK")
        print(f"Smoke vault: {vault}")
        if not args.keep:
            print("Temporary smoke vault will be removed. Use --keep to inspect it.")
        return 0
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if not args.keep:
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
