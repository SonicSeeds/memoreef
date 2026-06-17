from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from memoreef.bookmarks import Bookmark, bookmark_to_markdown, canonicalize_url, parse_bookmarks_html, parse_markdown_frontmatter, update_markdown_frontmatter, write_bookmarks_to_vault
from memoreef.cli import main
from memoreef.server import create_server, is_loopback_bind, review_mode_urls


class FakeHTTPHeaders:
    def __init__(self, charset=None):
        self.charset = charset

    def get_content_charset(self):
        return self.charset


class FakeHTTPResponse:
    def __init__(self, status: int, url: str = "https://example.com", body: bytes = b"ok", charset=None):
        self.status = status
        self.url = url
        self.body = body
        self.headers = FakeHTTPHeaders(charset)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, size=-1):
        if size is None or size < 0:
            return self.body
        return self.body[:size]


class BookmarkImportTests(unittest.TestCase):
    def test_parse_netscape_bookmarks(self):
        bookmarks = parse_bookmarks_html(Path(__file__).parent.parent / "examples" / "bookmarks.html")
        self.assertEqual(len(bookmarks), 3)
        self.assertEqual(bookmarks[0].title, "Local AI Agents for Small Teams")
        self.assertEqual(bookmarks[0].folders, ["AI Agents"])

    def test_write_obsidian_markdown(self):
        bookmarks = parse_bookmarks_html(Path(__file__).parent.parent / "examples" / "bookmarks.html")
        with tempfile.TemporaryDirectory() as tmp:
            written = write_bookmarks_to_vault(bookmarks[:1], tmp)
            self.assertEqual(len(written), 1)
            content = written[0].read_text(encoding="utf-8")
            self.assertIn("type: drop", content)
            self.assertIn("status: drift", content)
            self.assertIn("agent_ready: true", content)
            self.assertIn("Source: [https://example.com/local-agents]", content)

    def test_default_bookmark_writes_drift_triage_state(self):
        content = bookmark_to_markdown(Bookmark("Example", "https://example.com"))

        self.assertIn("status: drift", content)
        self.assertIn("pearl: false", content)

    def test_explicit_status_and_pearl_are_written(self):
        content = bookmark_to_markdown(Bookmark("Example", "https://example.com", status="reef", pearl=True))

        self.assertIn("status: reef", content)
        self.assertIn("pearl: true", content)

    def test_projects_are_written(self):
        content = bookmark_to_markdown(Bookmark("Example", "https://example.com", projects=["Project Alpha"]))

        self.assertIn("projects:\n  - \"Project Alpha\"", content)

    def test_shoals_are_written(self):
        content = bookmark_to_markdown(Bookmark("Example", "https://example.com", shoals=["Local AI"]))

        self.assertIn("shoals:\n  - \"Local AI\"", content)

    def test_triaged_at_is_written(self):
        content = bookmark_to_markdown(Bookmark("Example", "https://example.com", triaged_at="2026-06-11T12:00:00Z"))

        self.assertIn('triaged_at: "2026-06-11T12:00:00Z"', content)

    def test_title_with_internal_quotes_writes_valid_frontmatter(self):
        content = bookmark_to_markdown(Bookmark('Example "quoted" title', "https://example.com"))

        frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertIn('title: "Example \\"quoted\\" title"', content)
        self.assertEqual(frontmatter["title"], 'Example "quoted" title')

    def test_canonicalize_url_strips_tracking_params(self):
        self.assertEqual(
            canonicalize_url("HTTPS://Example.COM/CaseSensitive/Path?keep=1&utm_source=news&fbclid=abc&GCLID=xyz"),
            "https://example.com/CaseSensitive/Path?keep=1",
        )

    def test_write_skips_duplicate_canonical_urls_by_default(self):
        bookmarks = [
            Bookmark("First", "HTTPS://Example.COM/Case?keep=1&utm_campaign=spring"),
            Bookmark("Second", "https://example.com/Case?keep=1&fbclid=tracking"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            written = write_bookmarks_to_vault(bookmarks, tmp)

            self.assertEqual(len(written), 1)
            self.assertEqual(len(list((Path(tmp) / "MemoReef" / "Drops").glob("*.md"))), 1)

    def test_import_command_allows_duplicate_urls(self):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
  <DT><H3>Research</H3>
  <DL><p>
    <DT><A HREF="HTTPS://Example.COM/Case?keep=1&utm_source=news">First</A>
    <DT><A HREF="https://example.com/Case?keep=1&gclid=tracking">Second</A>
  </DL><p>
</DL><p>
"""
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            bookmarks_path = Path(tmp) / "bookmarks.html"
            vault_path = Path(tmp) / "vault"
            bookmarks_path.write_text(html, encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["import", str(bookmarks_path), "--vault", str(vault_path), "--allow-duplicates"])

            self.assertEqual(result, 0)
            self.assertEqual(len(list((vault_path / "MemoReef" / "Drops").glob("*.md"))), 2)

    def test_import_command_writes_import_log(self):
        html = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<DL><p>
  <DT><H3>Research</H3>
  <DL><p>
    <DT><A HREF="HTTPS://Example.COM/Case?keep=1&utm_source=news">First</A>
    <DT><A HREF="https://example.com/Case?keep=1&fbclid=tracking">Second</A>
  </DL><p>
</DL><p>
"""
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            bookmarks_path = Path(tmp) / "bookmarks.html"
            vault_path = Path(tmp) / "vault"
            bookmarks_path.write_text(html, encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["import", str(bookmarks_path), "--vault", str(vault_path)])

            logs = list((vault_path / "MemoReef" / "imports").glob("*-import.md"))
            self.assertEqual(result, 0)
            self.assertEqual(len(logs), 1)
            self.assertEqual(len(list((vault_path / "MemoReef" / "Drops").glob("*.md"))), 1)

            content = logs[0].read_text(encoding="utf-8")
            self.assertIn(f"- Source file: {bookmarks_path.resolve()}", content)
            self.assertIn("- Command options:", content)
            self.assertIn(f"  - vault: {vault_path.resolve()}", content)
            self.assertIn("  - root: MemoReef", content)
            self.assertIn("  - limit: None", content)
            self.assertIn("  - allow_duplicates: False", content)
            self.assertIn("- Parsed bookmark count: 2", content)
            self.assertIn("- Written Drop count: 1", content)
            self.assertIn("- Skipped duplicate count: 1", content)
            self.assertIn("- Errors/warnings:", content)
            self.assertIn("  - none", content)

    def test_import_links_uses_url_as_title_and_dedupes(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            links_path = Path(tmp) / "links.txt"
            vault_path = Path(tmp) / "vault"
            links_path.write_text(
                "\n".join(
                    [
                        "HTTPS://Example.COM/Alpha?utm_source=news",
                        "https://example.com/Alpha?fbclid=tracking",
                    ]
                ),
                encoding="utf-8",
            )

            with redirect_stdout(stdout):
                result = main(["import-links", str(links_path), "--vault", str(vault_path)])

            drops = list((vault_path / "MemoReef" / "Drops").glob("*.md"))
            logs = list((vault_path / "MemoReef" / "imports").glob("*-import.md"))

            self.assertEqual(result, 0)
            self.assertEqual(len(drops), 1)
            self.assertEqual(len(logs), 1)
            content = drops[0].read_text(encoding="utf-8")
            self.assertIn('title: "HTTPS://Example.COM/Alpha?utm_source=news"', content)
            self.assertIn("Source: [HTTPS://Example.COM/Alpha?utm_source=news]", content)
            self.assertIn("- Parsed bookmark count: 2", logs[0].read_text(encoding="utf-8"))
            self.assertIn("- Skipped duplicate count: 1", logs[0].read_text(encoding="utf-8"))

    def test_import_csv_preserves_title_and_tags(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "links.csv"
            vault_path = Path(tmp) / "vault"
            csv_path.write_text(
                "\n".join(
                    [
                        "title,url,source,tags",
                        'Article One,HTTPS://Example.COM/One?utm_source=news,newsletter,"research, ai"',
                        "Article Duplicate,https://example.com/One?gclid=tracking,newsletter,duplicate",
                    ]
                ),
                encoding="utf-8",
            )

            with redirect_stdout(stdout):
                result = main(["import-csv", str(csv_path), "--vault", str(vault_path)])

            drops = list((vault_path / "MemoReef" / "Drops").glob("*.md"))
            logs = list((vault_path / "MemoReef" / "imports").glob("*-import.md"))

            self.assertEqual(result, 0)
            self.assertEqual(len(drops), 1)
            self.assertEqual(len(logs), 1)
            content = drops[0].read_text(encoding="utf-8")
            self.assertIn('title: "Article One"', content)
            self.assertIn('import_source: "newsletter"', content)
            self.assertIn('  - "research"', content)
            self.assertIn('  - "ai"', content)
            log_content = logs[0].read_text(encoding="utf-8")
            self.assertIn("- Parsed bookmark count: 2", log_content)
            self.assertIn("- Written Drop count: 1", log_content)
            self.assertIn("- Skipped duplicate count: 1", log_content)

    def test_import_csv_omits_import_source_when_source_is_empty(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "links.csv"
            vault_path = Path(tmp) / "vault"
            csv_path.write_text(
                "\n".join(
                    [
                        "title,url,source,tags",
                        "Article One,https://example.com/one,,research",
                    ]
                ),
                encoding="utf-8",
            )

            with redirect_stdout(stdout):
                result = main(["import-csv", str(csv_path), "--vault", str(vault_path)])

            drops = list((vault_path / "MemoReef" / "Drops").glob("*.md"))
            self.assertEqual(result, 0)
            self.assertEqual(len(drops), 1)
            self.assertNotIn("import_source:", drops[0].read_text(encoding="utf-8"))

    def test_import_csv_omits_import_source_when_source_column_is_missing(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "links.csv"
            vault_path = Path(tmp) / "vault"
            csv_path.write_text(
                "\n".join(
                    [
                        "title,url,tags",
                        "Article One,https://example.com/one,research",
                    ]
                ),
                encoding="utf-8",
            )

            with redirect_stdout(stdout):
                result = main(["import-csv", str(csv_path), "--vault", str(vault_path)])

            drops = list((vault_path / "MemoReef" / "Drops").glob("*.md"))
            self.assertEqual(result, 0)
            self.assertEqual(len(drops), 1)
            self.assertNotIn("import_source:", drops[0].read_text(encoding="utf-8"))

    def test_import_docs_writes_text_document_drop(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "Research Note.txt"
            vault_path = Path(tmp) / "vault"
            doc_path.write_text("NotebookLM-style input\n\nMarkdown memory output", encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["import-docs", str(doc_path), "--vault", str(vault_path)])

            drops = list((vault_path / "MemoReef" / "Drops").glob("*.md"))
            logs = list((vault_path / "MemoReef" / "imports").glob("*-import.md"))
            content = drops[0].read_text(encoding="utf-8")
            frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertEqual(result, 0)
        self.assertEqual(len(drops), 1)
        self.assertEqual(len(logs), 1)
        self.assertEqual(frontmatter["has_document_text"], True)
        self.assertEqual(frontmatter["document_type"], "txt")
        self.assertIn("## Document text", content)
        self.assertIn("NotebookLM-style input", content)
        self.assertIn("Markdown memory output", content)

    def test_import_docs_extracts_docx_text(self):
        import zipfile

        stdout = io.StringIO()
        document_xml = """<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>
<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:body>
<w:p><w:r><w:t>First DOCX paragraph</w:t></w:r></w:p>
<w:p><w:r><w:t>Second DOCX paragraph</w:t></w:r></w:p>
</w:body></w:document>"""

        with tempfile.TemporaryDirectory() as tmp:
            doc_path = Path(tmp) / "Agent Brief.docx"
            vault_path = Path(tmp) / "vault"
            with zipfile.ZipFile(doc_path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)

            with redirect_stdout(stdout):
                result = main(["import-docs", str(doc_path), "--vault", str(vault_path)])

            content = next((vault_path / "MemoReef" / "Drops").glob("*.md")).read_text(encoding="utf-8")
            frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertEqual(result, 0)
        self.assertEqual(frontmatter["document_type"], "docx")
        self.assertIn("First DOCX paragraph", content)
        self.assertIn("Second DOCX paragraph", content)

    def test_import_docs_extracts_simple_pdf_text(self):
        stdout = io.StringIO()
        pdf_bytes = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj
4 0 obj << /Length 66 >> stream
BT /F1 12 Tf 72 720 Td (PDF source memory) Tj 0 -18 Td (Markdown vault output) Tj ET
endstream endobj
%%EOF
"""

        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "Source Memory.pdf"
            vault_path = Path(tmp) / "vault"
            pdf_path.write_bytes(pdf_bytes)

            with redirect_stdout(stdout):
                result = main(["import-docs", str(pdf_path), "--vault", str(vault_path)])

            content = next((vault_path / "MemoReef" / "Drops").glob("*.md")).read_text(encoding="utf-8")
            frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertEqual(result, 0)
        self.assertEqual(frontmatter["document_type"], "pdf")
        self.assertIn("PDF source memory", content)
        self.assertIn("Markdown vault output", content)

    def test_import_docs_rejects_unsupported_files(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.xlsx"
            path.write_text("not supported", encoding="utf-8")
            with redirect_stdout(stdout):
                result = main(["import-docs", str(path), "--vault", str(Path(tmp) / "vault")])

        self.assertEqual(result, 1)
        self.assertIn("Unsupported document type", stdout.getvalue())

    def test_import_docs_warns_for_image_without_ocr(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "diagram.png"
            vault_path = Path(tmp) / "vault"
            image_path.write_bytes(b"not really an image")

            with redirect_stdout(stdout):
                result = main(["import-docs", str(image_path), "--vault", str(vault_path)])

            content = next((vault_path / "MemoReef" / "Drops").glob("*.md")).read_text(encoding="utf-8")
            frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertEqual(result, 0)
        self.assertEqual(frontmatter["document_type"], "png")
        self.assertIn("_No extractable text found._", content)
        self.assertIn("image files need OCR", stdout.getvalue())

    def test_import_docs_ocr_image_with_local_tesseract(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_tesseract = bin_dir / "tesseract"
            fake_tesseract.write_text("#!/bin/sh\nprintf 'OCR source text\\nFrom diagram'\n", encoding="utf-8")
            fake_tesseract.chmod(0o755)
            image_path = Path(tmp) / "diagram.png"
            vault_path = Path(tmp) / "vault"
            image_path.write_bytes(b"not really an image")

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
            try:
                with redirect_stdout(stdout):
                    result = main(["import-docs", "--ocr", str(image_path), "--vault", str(vault_path)])
            finally:
                os.environ["PATH"] = old_path

            content = next((vault_path / "MemoReef" / "Drops").glob("*.md")).read_text(encoding="utf-8")
            frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertEqual(result, 0)
        self.assertEqual(frontmatter["document_type"], "png")
        self.assertIn('  - "ocr"', content)
        self.assertIn("OCR source text", content)
        self.assertIn("From diagram", content)

    def test_import_docs_ocr_pdf_warns_without_renderer(self):
        stdout = io.StringIO()
        pdf_bytes = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake_tesseract = bin_dir / "tesseract"
            fake_tesseract.write_text("#!/bin/sh\nprintf 'OCR text'\n", encoding="utf-8")
            fake_tesseract.chmod(0o755)
            pdf_path = Path(tmp) / "scan.pdf"
            vault_path = Path(tmp) / "vault"
            pdf_path.write_bytes(pdf_bytes)

            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(bin_dir)
            try:
                with redirect_stdout(stdout):
                    result = main(["import-docs", "--ocr", str(pdf_path), "--vault", str(vault_path)])
            finally:
                os.environ["PATH"] = old_path

            content = next((vault_path / "MemoReef" / "Drops").glob("*.md")).read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertIn("_No extractable text found._", content)
        self.assertIn("pdftoppm", stdout.getvalue())

    def test_inspect_command_prints_summary(self):
        bookmarks_path = Path(__file__).parent.parent / "examples" / "bookmarks.html"
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = main(["inspect", str(bookmarks_path)])

        self.assertEqual(result, 0)
        self.assertEqual(
            stdout.getvalue(),
            "\n".join(
                [
                    "Total bookmarks: 3",
                    "Top-level folders:",
                    "- AI Agents: 2",
                    "- Creative Research: 1",
                    "",
                ]
            ),
        )

    def test_inspect_command_does_not_create_vault_files(self):
        bookmarks_path = Path(__file__).parent.parent / "examples" / "bookmarks.html"
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            previous_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with redirect_stdout(stdout):
                    result = main(["inspect", str(bookmarks_path)])
            finally:
                os.chdir(previous_cwd)

            self.assertEqual(result, 0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_export_review_session_explicit_output(self):
        stdout = io.StringIO()
        bookmarks = [
            Bookmark(
                "Example Source",
                "https://example.com",
                folders=["AI Agents"],
                tags=["research"],
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "review-session.json"
            write_bookmarks_to_vault(bookmarks, vault_path)

            with redirect_stdout(stdout):
                result = main(["export-review-session", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            drop = data["drops"][0]
            self.assertEqual(result, 0)
            self.assertEqual(data["version"], 1)
            self.assertIn("created_at", data)
            self.assertEqual(data["stats"], {"total": 1, "drift": 1})
            self.assertEqual(drop["id"], drop["path"])
            self.assertTrue(drop["path"].startswith("MemoReef/Drops/"))
            self.assertEqual(drop["title"], "Example Source")
            self.assertEqual(drop["url"], "https://example.com")
            self.assertEqual(drop["status"], "drift")
            self.assertEqual(drop["pearl"], False)
            self.assertEqual(drop["folders"], ["AI Agents"])
            self.assertEqual(drop["tags"], ["research", "ai-agents"])
            self.assertEqual(drop["summary"], "_Not enriched yet._")

    def test_export_review_session_default_output_path(self):
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)

            with redirect_stdout(stdout):
                result = main(["export-review-session", "--vault", str(vault_path)])

            outputs = list((vault_path / "MemoReef" / "review-sessions").glob("*-review-session.json"))
            self.assertEqual(result, 0)
            self.assertEqual(len(outputs), 1)
            data = json.loads(outputs[0].read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["stats"]["total"], 1)
            self.assertEqual(len(data["drops"]), 1)

    def update_drop_frontmatter(self, path: Path, updates: dict[str, object]) -> None:
        content = path.read_text(encoding="utf-8")
        path.write_text(update_markdown_frontmatter(content, updates), encoding="utf-8")

    def export_session_data(self, vault_path: Path, *args: str):
        stdout = io.StringIO()
        output_path = vault_path.parent / "review-session.json"
        with redirect_stdout(stdout):
            result = main(["export-review-session", "--vault", str(vault_path), "--output", str(output_path), *args])
        return result, stdout.getvalue(), json.loads(output_path.read_text(encoding="utf-8"))

    def test_export_review_session_no_filters_writes_default_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("One", "https://one.example")], vault_path)

            result, output, data = self.export_session_data(vault_path)

            self.assertEqual(result, 0)
            self.assertEqual(len(data["drops"]), 1)
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(data["filters"]["project"], [])
            self.assertEqual(data["filters"]["shoal"], [])
            self.assertEqual(data["filters"]["pearl_only"], False)
            self.assertIsNone(data["filters"]["limit"])
            self.assertIn("- filters: none", output)

    def test_export_review_session_filters_project_shoal_status_tag_folder_and_pearl(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Match", "https://match.example", projects=["AI Agents"], shoals=["Automation"], status="reef", pearl=True, folders=["Inbox"], tags=["agents"]),
                Bookmark("Other", "https://other.example", projects=["Other"], shoals=["Automation"], status="drift", folders=["Inbox"], tags=["agents"]),
            ], vault_path, allow_duplicates=True)

            result, output, data = self.export_session_data(
                vault_path,
                "--project",
                "ai agents",
                "--shoal",
                "automation",
                "--status",
                "REEF",
                "--tag",
                "Agents",
                "--folder",
                "inbox",
                "--pearl-only",
            )

            self.assertEqual(result, 0)
            self.assertEqual([item["title"] for item in data["items"]], ["Match"])
            self.assertIn("project=ai agents", output)
            self.assertIn("pearl-only=true", output)

    def test_export_review_session_filters_hostname_metadata_and_url_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Metadata Host", "https://wrong.example/a"),
                Bookmark("URL Host", "https://fallback.example/b"),
                Bookmark("No Match", "https://other.example/c"),
            ], vault_path, allow_duplicates=True)
            self.update_drop_frontmatter(written[0], {"hostname": "meta.example"})

            result, _output, data = self.export_session_data(
                vault_path,
                "--hostname",
                "META.EXAMPLE",
                "--hostname",
                "fallback.example",
            )

            self.assertEqual(result, 0)
            self.assertEqual([item["title"] for item in data["items"]], ["Metadata Host", "URL Host"])

    def test_export_review_session_exclude_status_and_and_logic(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Drift Project", "https://one.example", projects=["AI Agents"], status="drift"),
                Bookmark("Reef Project", "https://two.example", projects=["AI Agents"], status="reef"),
                Bookmark("Discarded Project", "https://three.example", projects=["AI Agents"], status="discarded"),
                Bookmark("Other Drift", "https://four.example", projects=["Other"], status="drift"),
            ], vault_path, allow_duplicates=True)

            result, _output, data = self.export_session_data(
                vault_path,
                "--project",
                "AI Agents",
                "--status",
                "drift",
                "--status",
                "reef",
                "--exclude-status",
                "discarded",
            )

            self.assertEqual(result, 0)
            self.assertEqual([item["title"] for item in data["items"]], ["Drift Project", "Reef Project"])

    def test_export_review_session_limit_applies_after_filtering(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("One", "https://one.example", status="drift"),
                Bookmark("Two", "https://two.example", status="drift"),
                Bookmark("Three", "https://three.example", status="drift"),
            ], vault_path, allow_duplicates=True)

            result, output, data = self.export_session_data(vault_path, "--status", "drift", "--limit", "2")

            self.assertEqual(result, 0)
            self.assertEqual(len(data["items"]), 2)
            self.assertEqual(data["filters"]["limit"], 2)
            self.assertIn("limit=2", output)

    def test_app_workflow_mentions_filtered_review_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"

            with redirect_stdout(io.StringIO()):
                result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("filtered", html.lower())
            self.assertIn("export-review-session", html)

    def test_readme_and_tasks_mention_filtered_review_sessions(self):
        readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        tasks = (Path(__file__).parent.parent / "docs" / "CODEX_TASKS.md").read_text(encoding="utf-8")

        self.assertIn("filtered review", readme.lower())
        self.assertIn("Task 19", tasks)
        self.assertIn("Filtered review sessions", tasks)

    def search_library_data(self, vault_path: Path, *args: str):
        stdout = io.StringIO()
        output_path = vault_path.parent / "search-results.json"
        with redirect_stdout(stdout):
            result = main(["search-library", "--vault", str(vault_path), "--query", "agent workflow", "--output", str(output_path), *args])
        return result, stdout.getvalue(), json.loads(output_path.read_text(encoding="utf-8"))

    def append_drop_body(self, path: Path, text: str) -> None:
        path.write_text(path.read_text(encoding="utf-8") + "\n" + text + "\n", encoding="utf-8")

    def test_search_library_basic_title_and_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Agent Workflow Guide", "https://title.example"),
                Bookmark("Body Only", "https://body.example"),
            ], vault_path, allow_duplicates=True)
            self.append_drop_body(written[1], "agent workflow appears in the body")

            result, output, data = self.search_library_data(vault_path)

            self.assertEqual(result, 0)
            self.assertEqual(data["query"], "agent workflow")
            self.assertEqual(data["summary"]["matches"], 2)
            self.assertEqual(data["items"][0]["title"], "Agent Workflow Guide")
            self.assertIn("title", data["items"][0]["matched_fields"])
            self.assertTrue(data["items"][0]["score"] > data["items"][1]["score"])
            self.assertIn("Search library:", output)
            self.assertIn("- filters: none", output)

    def test_search_library_matches_body_summary_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Plain Body", "https://body.example"),
                Bookmark("Label Source", "https://labels.example", projects=["AI Agents"], shoals=["Automation"], folders=["Inbox"], tags=["workflow"]),
            ], vault_path, allow_duplicates=True)
            self.append_drop_body(written[0], "A body-only agent workflow note.")

            result, _output, data = self.search_library_data(vault_path)
            fields = {item["title"]: set(item["matched_fields"]) for item in data["items"]}

            self.assertEqual(result, 0)
            self.assertIn("body", fields["Plain Body"])
            self.assertTrue({"projects", "shoals", "tags"} & fields["Label Source"])

    def test_search_library_matches_hostname_and_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Host Match", "https://example.com/agent-workflow"),
                Bookmark("Metadata Host", "https://wrong.example/elsewhere"),
            ], vault_path, allow_duplicates=True)
            self.update_drop_frontmatter(written[1], {"hostname": "agent-workflow.example"})

            result, _output, data = self.search_library_data(vault_path)
            titles = [item["title"] for item in data["items"]]

            self.assertEqual(result, 0)
            self.assertIn("Host Match", titles)
            self.assertIn("Metadata Host", titles)

    def test_search_library_filters_limit_pearl_and_exclude_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Agent Workflow Pearl", "https://one.example", projects=["AI Agents"], status="drift", pearl=True),
                Bookmark("Agent Workflow Discarded", "https://two.example", projects=["AI Agents"], status="discarded", pearl=True),
                Bookmark("Agent Workflow Other", "https://three.example", projects=["Other"], status="drift", pearl=True),
            ], vault_path, allow_duplicates=True)

            result, _output, data = self.search_library_data(
                vault_path,
                "--project",
                "AI Agents",
                "--pearl-only",
                "--exclude-status",
                "discarded",
                "--limit",
                "1",
            )

            self.assertEqual(result, 0)
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(data["items"][0]["title"], "Agent Workflow Pearl")
            self.assertEqual(data["filters"]["project"], ["AI Agents"])
            self.assertTrue(data["filters"]["pearl_only"])
            self.assertEqual(data["filters"]["exclude_status"], ["discarded"])
            self.assertEqual(data["filters"]["limit"], 1)

    def test_search_library_default_output_under_search_and_explicit_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            explicit = Path(tmp) / "explicit-search.json"
            write_bookmarks_to_vault([Bookmark("Agent Workflow", "https://example.com")], vault_path)

            with redirect_stdout(io.StringIO()):
                default_result = main(["search-library", "--vault", str(vault_path), "--query", "agent"])
            with redirect_stdout(io.StringIO()):
                explicit_result = main(["search-library", "--vault", str(vault_path), "--query", "agent", "--output", str(explicit)])

            outputs = list((vault_path / "MemoReef" / "search").glob("*-search-results.json"))
            self.assertEqual(default_result, 0)
            self.assertEqual(explicit_result, 0)
            self.assertEqual(len(outputs), 1)
            self.assertTrue(explicit.exists())

    def brief_text(self, vault_path: Path, *args: str):
        stdout = io.StringIO()
        output_path = vault_path.parent / "project-brief.md"
        with redirect_stdout(stdout):
            result = main(["brief", "--vault", str(vault_path), "--output", str(output_path), *args])
        return result, stdout.getvalue(), output_path.read_text(encoding="utf-8")

    def test_brief_generation_with_project_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Agent Context Source", "https://agent.example/context", projects=["AI Agents"], tags=["agents"], status="reef"),
                Bookmark("Design Source", "https://design.example/source", projects=["Design Systems"], tags=["design"], status="reef"),
            ], vault_path, allow_duplicates=True)

            result, output, text = self.brief_text(vault_path, "--project", "AI Agents")

            self.assertEqual(result, 0)
            self.assertIn("- sources: 1", output)
            self.assertIn("Agent Context Source", text)
            self.assertNotIn("Design Source", text)
            self.assertIn("Applied filters: project=AI Agents", text)
            self.assertIn("Agent handoff", text)
            self.assertIn("https://agent.example/context", text)

    def test_brief_respects_pearl_status_tag_and_limit_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("First Pearl", "https://one.example", projects=["AI Agents"], tags=["agents"], status="reef", pearl=True),
                Bookmark("Second Pearl", "https://two.example", projects=["AI Agents"], tags=["agents"], status="reef", pearl=True),
                Bookmark("Wrong Status", "https://drift.example", projects=["AI Agents"], tags=["agents"], status="drift", pearl=True),
                Bookmark("Wrong Tag", "https://tag.example", projects=["AI Agents"], tags=["other"], status="reef", pearl=True),
                Bookmark("Not Pearl", "https://plain.example", projects=["AI Agents"], tags=["agents"], status="reef", pearl=False),
            ], vault_path, allow_duplicates=True)

            result, _output, text = self.brief_text(
                vault_path,
                "--project",
                "AI Agents",
                "--status",
                "reef",
                "--tag",
                "agents",
                "--pearl-only",
                "--limit",
                "1",
            )

            self.assertEqual(result, 0)
            self.assertIn("Selected sources: 1", text)
            self.assertIn("First Pearl", text)
            self.assertNotIn("Second Pearl", text)
            self.assertNotIn("Wrong Status", text)
            self.assertNotIn("Wrong Tag", text)
            self.assertNotIn("Not Pearl", text)

    def test_brief_does_not_modify_drop_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Read Only Source", "https://readonly.example", projects=["AI Agents"], status="reef"),
            ], vault_path)
            before = {path: path.read_text(encoding="utf-8") for path in written}

            result, _output, text = self.brief_text(vault_path, "--project", "AI Agents")

            self.assertEqual(result, 0)
            self.assertIn("Read Only Source", text)
            self.assertEqual(before, {path: path.read_text(encoding="utf-8") for path in written})

    def test_app_writes_library_page_and_dashboard_mentions_library_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("Agent Workflow", "https://example.com")], vault_path)
            with redirect_stdout(io.StringIO()):
                main(["search-library", "--vault", str(vault_path), "--query", "agent"])

            with redirect_stdout(io.StringIO()):
                result = main(["app", "--vault", str(vault_path)])

            app_dir = vault_path / "MemoReef" / "app"
            index = (app_dir / "index.html").read_text(encoding="utf-8")
            library = (app_dir / "library.html").read_text(encoding="utf-8")
            detail_pages = list((app_dir / "drops").glob("*.html"))
            self.assertEqual(result, 0)
            self.assertIn("Library/Search", index)
            self.assertIn("library.html", index)
            self.assertIn("review.html", index)
            self.assertIn("reports.html", index)
            self.assertIn("briefs.html", index)
            self.assertIn("search-library", library)
            self.assertIn("Agent Workflow", library)
            self.assertIn("drops/", library)
            self.assertTrue(detail_pages)
            detail = detail_pages[0].read_text(encoding="utf-8")
            self.assertIn("Agent Workflow", detail)
            self.assertIn("Markdown path", detail)

    def test_pilot_command_imports_bookmarks_and_creates_guided_artifacts(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "pilot-vault"
            source = Path(__file__).parent.parent / "examples" / "bookmarks.html"
            before = source.read_text(encoding="utf-8")

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=AssertionError("network call")):
                with redirect_stdout(stdout):
                    result = main(["pilot", "--bookmarks", str(source), "--vault", str(vault_path), "--review-limit", "2"])

            root = vault_path / "MemoReef"
            drops = list((root / "Drops").glob("*.md"))
            review_sessions = list((root / "review-sessions").glob("*-review-session.json"))
            duplicate_reports = list((root / "reports").glob("*-duplicate-report.json"))
            pilot_readme = root / "PILOT_README.md"
            pilot_page = root / "app" / "pilot.html"
            self.assertEqual(result, 0)
            self.assertTrue(drops)
            self.assertEqual(len(review_sessions), 1)
            self.assertEqual(len(duplicate_reports), 1)
            self.assertTrue((root / "app" / "index.html").exists())
            self.assertTrue((root / "app" / "tour.html").exists())
            self.assertTrue(pilot_page.exists())
            self.assertTrue(pilot_readme.exists())
            self.assertEqual(source.read_text(encoding="utf-8"), before)
            self.assertIn("Created MemoReef pilot vault:", stdout.getvalue())
            self.assertIn("Start here", pilot_readme.read_text(encoding="utf-8"))
            self.assertIn("feedback", pilot_page.read_text(encoding="utf-8").lower())

    def test_pilot_supports_links_and_csv_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            links = base / "links.txt"
            links.write_text("https://links.example/one\nhttps://links.example/two\n", encoding="utf-8")
            csv_path = base / "links.csv"
            csv_path.write_text("title,url,source,tags\nCSV Source,https://csv.example/one,test,alpha beta\n", encoding="utf-8")
            links_vault = base / "links-vault"
            csv_vault = base / "csv-vault"

            with redirect_stdout(io.StringIO()):
                links_result = main(["pilot", "--links", str(links), "--vault", str(links_vault), "--skip-reports"])
            with redirect_stdout(io.StringIO()):
                csv_result = main(["pilot", "--csv", str(csv_path), "--vault", str(csv_vault), "--review-limit", "1"])

            self.assertEqual(links_result, 0)
            self.assertEqual(csv_result, 0)
            self.assertTrue(list((links_vault / "MemoReef" / "Drops").glob("*.md")))
            self.assertFalse((links_vault / "MemoReef" / "reports").exists())
            self.assertTrue(list((csv_vault / "MemoReef" / "Drops").glob("*.md")))
            self.assertTrue((csv_vault / "MemoReef" / "app" / "pilot.html").exists())

    def test_pilot_does_not_modify_files_outside_selected_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "links.txt"
            outside = base / "outside.txt"
            source.write_text("https://offline.example/source\n", encoding="utf-8")
            outside.write_text("do not touch\n", encoding="utf-8")
            before_source = source.read_text(encoding="utf-8")
            before_outside = outside.read_text(encoding="utf-8")

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=AssertionError("network call")):
                with redirect_stdout(io.StringIO()):
                    result = main(["pilot", "--links", str(source), "--vault", str(base / "vault")])

            self.assertEqual(result, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), before_source)
            self.assertEqual(outside.read_text(encoding="utf-8"), before_outside)

    def test_app_generates_pilot_page_and_nav_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("Pilot Source", "https://pilot.example")], vault_path)
            (vault_path / "MemoReef" / "PILOT_README.md").write_text("# MemoReef Pilot Checklist\n\n## Start here\n", encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                result = main(["app", "--vault", str(vault_path)])

            app_dir = vault_path / "MemoReef" / "app"
            index = (app_dir / "index.html").read_text(encoding="utf-8")
            tour = (app_dir / "tour.html").read_text(encoding="utf-8")
            pilot = (app_dir / "pilot.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("pilot.html", index)
            self.assertIn("pilot.html", tour)
            self.assertIn("Pilot checklist", pilot)
            self.assertIn("Review Mode", pilot)

    def test_pilot_check_reports_missing_and_ready_artifacts(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"

            with redirect_stdout(stdout):
                missing = main(["pilot-check", "--vault", str(vault_path)])

            self.assertEqual(missing, 1)
            self.assertIn("missing: Drops", stdout.getvalue())

            links = Path(tmp) / "links.txt"
            links.write_text("https://ready.example/source\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                main(["pilot", "--links", str(links), "--vault", str(vault_path)])
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                ready = main(["pilot-check", "--vault", str(vault_path)])

            self.assertEqual(ready, 0)
            self.assertIn("ok: app/pilot.html", stdout.getvalue())

    def test_readme_and_tasks_mention_search_library(self):
        readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        tasks = (Path(__file__).parent.parent / "docs" / "CODEX_TASKS.md").read_text(encoding="utf-8")

        self.assertIn("search-library", readme)
        self.assertIn("Task 20", tasks)
        self.assertIn("Library search", tasks)

    def write_decisions(self, path: Path, drop_path: Path, vault_path: Path, decision: str, reviewed_at: str = "2026-06-12T12:45:00Z"):
        relative = drop_path.resolve().relative_to(vault_path.resolve()).as_posix()
        payload = {
            "version": 1,
            "reviewed_at": reviewed_at,
            "decisions": [
                {
                    "id": relative,
                    "path": relative,
                    "decision": decision,
                    "status": "reef",
                    "pearl": decision == "pearl",
                }
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_apply_review_decisions_keep_updates_frontmatter(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_decisions(decisions_path, written[0], vault_path, "keep")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            content = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("Applied review decisions:", stdout.getvalue())
            self.assertIn("- updated: 1", stdout.getvalue())
            self.assertIn("status: reef", content)
            self.assertIn("pearl: false", content)
            self.assertIn('triaged_at: "2026-06-12T12:45:00Z"', content)

    def test_apply_review_decisions_pearl_updates_frontmatter(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_decisions(decisions_path, written[0], vault_path, "pearl")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            content = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("status: reef", content)
            self.assertIn("pearl: true", content)

    def test_apply_review_decisions_sink_moves_drop_to_discarded_with_delete_after(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_decisions(decisions_path, written[0], vault_path, "sink")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            discarded = vault_path / "MemoReef" / "Discarded" / written[0].name
            content = discarded.read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertFalse(written[0].exists())
            self.assertTrue(discarded.exists())
            self.assertIn("status: discarded", content)
            self.assertIn("pearl: false", content)
            self.assertIn("discarded_at: \"2026-06-12T12:45:00Z\"", content)
            self.assertIn("delete_after: \"2026-07-12T12:45:00Z\"", content)

    def test_apply_review_decisions_dry_run_does_not_modify_file(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")
            decisions_path = Path(tmp) / "decisions.json"
            self.write_decisions(decisions_path, written[0], vault_path, "pearl")

            with redirect_stdout(stdout):
                result = main([
                    "apply-review-decisions",
                    "--vault",
                    str(vault_path),
                    "--decisions",
                    str(decisions_path),
                    "--dry-run",
                ])

            self.assertEqual(result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)
            self.assertIn("Dry run review decisions:", stdout.getvalue())
            self.assertIn("- would update: 1", stdout.getvalue())

    def test_apply_review_decisions_missing_file_warns_and_skips(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            vault_path.mkdir()
            decisions_path = Path(tmp) / "decisions.json"
            payload = {
                "version": 1,
                "reviewed_at": "2026-06-12T12:45:00Z",
                "decisions": [{"path": "MemoReef/Drops/missing.md", "decision": "keep"}],
            }
            decisions_path.write_text(json.dumps(payload), encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            self.assertEqual(result, 0)
            self.assertIn("- skipped: 1", stdout.getvalue())
            self.assertIn("file not found", stdout.getvalue())

    def test_apply_review_decisions_blocks_path_traversal(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            vault_path.mkdir()
            outside = Path(tmp) / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            decisions_path = Path(tmp) / "decisions.json"
            payload = {
                "version": 1,
                "reviewed_at": "2026-06-12T12:45:00Z",
                "decisions": [{"path": "../outside.md", "decision": "keep"}],
            }
            decisions_path.write_text(json.dumps(payload), encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            self.assertEqual(result, 0)
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")
            self.assertIn("path is outside MemoReef Drops", stdout.getvalue())

    def test_apply_review_decisions_preserves_existing_fields_and_body(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            bookmark = Bookmark(
                "Example Source",
                "https://example.com",
                folders=["AI Agents"],
                tags=["research"],
                projects=["MemoReef"],
                shoals=["Agent Memory"],
            )
            written = write_bookmarks_to_vault([bookmark], vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_decisions(decisions_path, written[0], vault_path, "keep")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            content = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn('title: "Example Source"', content)
            self.assertIn('url: "https://example.com"', content)
            self.assertIn("folders:", content)
            self.assertIn("tags:", content)
            self.assertIn("projects:", content)
            self.assertIn("shoals:", content)
            self.assertIn("## Summary", content)
            self.assertIn("## Agent Brief", content)

    def test_local_server_review_session_and_decision_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault(
                [
                    Bookmark("Drift Source", "https://drift.example", status="drift"),
                    Bookmark("Reef Source", "https://reef.example", status="reef"),
                ],
                vault_path,
                allow_duplicates=True,
            )
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urllib.request.urlopen(f"{base_url}/api/status", timeout=5) as response:
                    status_code = response.status
                    status = json.loads(response.read().decode("utf-8"))

                self.assertEqual(status_code, 200)
                self.assertEqual(status["ok"], True)
                self.assertEqual(status["vault"], str(vault_path.resolve()))
                self.assertEqual(status["root"], "MemoReef")

                with urllib.request.urlopen(f"{base_url}/api/review-session", timeout=5) as response:
                    session_status = response.status
                    session = json.loads(response.read().decode("utf-8"))

                self.assertEqual(session_status, 200)
                self.assertEqual([drop["title"] for drop in session["drops"]], ["Drift Source"])
                self.assertEqual(session["filters"]["status"], ["drift"])
                self.assertEqual(session["filters"]["limit"], 50)

                relative = written[0].resolve().relative_to(vault_path.resolve()).as_posix()
                payload = {
                    "version": 1,
                    "reviewed_at": "2026-06-14T12:00:00Z",
                    "decisions": [{"id": relative, "path": relative, "decision": "pearl"}],
                }
                request = urllib.request.Request(
                    f"{base_url}/api/review-decisions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    result_status = response.status
                    result = json.loads(response.read().decode("utf-8"))

                frontmatter, _body = parse_markdown_frontmatter(written[0].read_text(encoding="utf-8"))
                self.assertEqual(result_status, 200)
                self.assertEqual(result["updated"], 1)
                self.assertEqual(result["skipped"], 0)
                self.assertEqual(frontmatter["status"], "reef")
                self.assertEqual(frontmatter["pearl"], True)
                self.assertEqual(frontmatter["triaged_at"], "2026-06-14T12:00:00Z")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

    def test_local_server_drop_endpoint_writes_url_and_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/drop",
                    data=json.dumps({"url": " https://example.com/page ", "title": " Page title "}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    status_code = response.status
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            written = [Path(path) for path in payload["written"]]
            content = written[0].read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["clipped"], False)
        self.assertEqual(len(written), 1)
        self.assertTrue(written[0].is_absolute())
        self.assertIn('title: "Page title"', content)
        self.assertIn('url: "https://example.com/page"', content)
        self.assertNotIn("has_clipped_selection", content)
        self.assertNotIn("## Clipped selection", content)
        self.assertIn("# Page title", content)

    def test_local_server_drop_endpoint_writes_and_truncates_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            selection = "First selected line\n" + ("x" * 4100)
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/drop",
                    data=json.dumps({"url": "https://example.com/selection", "title": "", "selection": selection}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

            written = Path(payload["written"][0])
            content = written.read_text(encoding="utf-8")
            frontmatter, _body = parse_markdown_frontmatter(content)

        self.assertEqual(frontmatter["title"], "https://example.com/selection")
        self.assertEqual(frontmatter["has_clipped_selection"], True)
        self.assertEqual(frontmatter["clip_type"], "highlight")
        self.assertEqual(payload["clipped"], True)
        self.assertIn("## Clipped selection", content)
        self.assertIn("> First selected line", content)
        self.assertIn("> " + ("x" * 3980), content)
        self.assertNotIn("x" * 4001, content)

    def test_local_server_drop_endpoint_rejects_invalid_json_and_missing_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                invalid_request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/drop",
                    data=b"{",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as invalid_error:
                    urllib.request.urlopen(invalid_request, timeout=5)

                missing_url_request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_port}/api/drop",
                    data=json.dumps({"title": "No URL"}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as missing_error:
                    urllib.request.urlopen(missing_url_request, timeout=5)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(invalid_error.exception.code, 400)
        self.assertEqual(missing_error.exception.code, 400)
        self.assertFalse((vault_path / "MemoReef" / "Drops").exists())

    def test_local_server_api_options_returns_cors_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/drop", method="OPTIONS")
                with urllib.request.urlopen(request, timeout=5) as response:
                    status_code = response.status
                    headers = response.headers
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(status_code, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, POST, OPTIONS")
        self.assertEqual(headers["Access-Control-Allow-Headers"], "Content-Type")

    def test_local_server_options_rejects_non_bookmarklet_api_cors(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/review-decisions", method="OPTIONS")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request, timeout=5)
                headers = error.exception.headers
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertEqual(error.exception.code, 404)
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))

    def test_review_mode_urls_include_localhost_and_lan_addresses(self):
        self.assertTrue(is_loopback_bind("127.0.0.1"))
        self.assertTrue(is_loopback_bind("localhost"))
        self.assertFalse(is_loopback_bind("0.0.0.0"))

        urls = review_mode_urls("0.0.0.0", 8765, ["192.168.1.23", "100.64.0.5"])

        self.assertEqual(urls[0], "http://localhost:8765/")
        self.assertIn("http://192.168.1.23:8765/", urls)
        self.assertIn("http://100.64.0.5:8765/", urls)
        self.assertIn("http://0.0.0.0:8765/", urls)

    def test_serve_mobile_option_binds_all_interfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("memoreef.server.serve") as mocked_serve:
                result = main(["serve", "--vault", tmp, "--mobile", "--port", "9999", "--limit", "3"])

        self.assertEqual(result, 0)
        mocked_serve.assert_called_once_with(Path(tmp), "MemoReef", "0.0.0.0", 9999, 3)

    def test_phone_command_prints_user_owned_phone_urls_and_writes_url_file(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            with patch("memoreef.server.local_ipv4_addresses", return_value=["192.168.1.23"]), patch("memoreef.server.serve") as mocked_serve:
                with redirect_stdout(stdout):
                    result = main(["phone", "--vault", str(vault_path), "--port", "9999", "--limit", "3", "--no-qr"])

            url_file = vault_path.resolve() / "MemoReef" / "phone-triage-url.txt"
            output = stdout.getvalue()
            url_file_exists = url_file.exists()
            url_file_content = url_file.read_text(encoding="utf-8").strip()

        self.assertEqual(result, 0)
        self.assertTrue(url_file_exists)
        self.assertEqual(url_file_content, "http://192.168.1.23:9999/")
        self.assertIn("MemoReef phone triage for this computer", output)
        self.assertIn("http://192.168.1.23:9999/", output)
        mocked_serve.assert_called_once_with(vault_path, "MemoReef", "0.0.0.0", 9999, 3)

    def test_phone_command_writes_qr_when_qr_helper_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            with patch("memoreef.server.local_ipv4_addresses", return_value=["100.64.0.5"]), patch("memoreef.server.serve"), patch("memoreef.cli.write_optional_qr_png", return_value=(Path(tmp) / "qr.png", None)) as mocked_qr:
                result = main(["phone", "--vault", str(vault_path), "--port", "9999"])

        self.assertEqual(result, 0)
        mocked_qr.assert_called_once_with("http://100.64.0.5:9999/", vault_path.resolve() / "MemoReef" / "phone-triage-qr.png")

    def test_tag_reviewed_adds_tags_only_to_kept_and_pearl_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault(
                [
                    Bookmark("Local-first agent research workflow", "https://research.example/agent-workflow", folders=["AI Agents"], status="reef"),
                    Bookmark("Hydration plant care rituals", "https://garden.example/hydration-plants", folders=["Product Design"], status="reef", pearl=True),
                    Bookmark("Random coupon page", "https://coupon.example/deals", folders=["Inbox"], status="drift"),
                ],
                vault_path,
                allow_duplicates=True,
            )
            result = main(["tag-reviewed", "--vault", str(vault_path)])
            kept_frontmatter, _ = parse_markdown_frontmatter(written[0].read_text(encoding="utf-8"))
            pearl_frontmatter, _ = parse_markdown_frontmatter(written[1].read_text(encoding="utf-8"))
            drift_frontmatter, _ = parse_markdown_frontmatter(written[2].read_text(encoding="utf-8"))

        self.assertEqual(result, 0)
        kept_tags = kept_frontmatter.get("tags", [])
        pearl_tags = pearl_frontmatter.get("tags", [])
        if not isinstance(kept_tags, list) or not isinstance(pearl_tags, list):
            self.fail("expected tag lists")
        self.assertIn("ai-agents", kept_tags)
        self.assertIn("agent", kept_tags)
        self.assertIn("product-design", pearl_tags)
        self.assertIn("hydration", pearl_tags)
        self.assertIn("agent_tagged_at", kept_frontmatter)
        self.assertNotIn("agent_tagged_at", drift_frontmatter)

    def test_tag_reviewed_dry_run_does_not_modify_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault(
                [Bookmark("Searchable markdown archives", "https://archive.example/search", folders=["Knowledge Management"], status="reef")],
                vault_path,
                allow_duplicates=True,
            )
            before = written[0].read_text(encoding="utf-8")
            result = main(["tag-reviewed", "--vault", str(vault_path), "--dry-run"])
            after = written[0].read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertEqual(after, before)

    def test_local_server_tag_reviewed_endpoint_updates_reviewed_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault(
                [Bookmark("Biopunk moss specimen design", "https://moss.example/specimen", folders=["Design Systems"], status="reef")],
                vault_path,
                allow_duplicates=True,
            )
            try:
                server = create_server(vault_path, host="127.0.0.1", port=0, limit=50)
            except PermissionError as error:
                self.skipTest(f"localhost socket binding unavailable: {error}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_port
                request = urllib.request.Request(f"http://127.0.0.1:{port}/api/tag-reviewed", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                frontmatter, _ = parse_markdown_frontmatter(written[0].read_text(encoding="utf-8"))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["updated"], 1)
        endpoint_tags = frontmatter.get("tags", [])
        if not isinstance(endpoint_tags, list):
            self.fail("expected endpoint tag list")
        self.assertIn("biopunk", endpoint_tags)
        self.assertIn("agent_tagged_at", frontmatter)

    def write_plan_decisions(self, path: Path, vault_path: Path, items: list[tuple[Path, str]]):
        decisions = []
        for drop_path, decision in items:
            relative = drop_path.resolve().relative_to(vault_path.resolve()).as_posix()
            decisions.append({"id": relative, "path": relative, "decision": decision})
        path.write_text(json.dumps({"version": 1, "reviewed_at": "2026-06-12T13:00:00Z", "decisions": decisions}), encoding="utf-8")

    def test_plan_agent_finish_explicit_output_groups_examples_and_remaining(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "agent-finish-plan.json"
            bookmarks = [
                Bookmark("Pearl Source", "https://pearl.example", folders=["AI Agents"]),
                Bookmark("Keep Source", "https://keep.example", folders=["Research"]),
                Bookmark("Sink Source", "https://sink.example", folders=["Noise"]),
                Bookmark("Remaining Source", "https://remaining.example", folders=["Later"]),
            ]
            written = write_bookmarks_to_vault(bookmarks, vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_plan_decisions(decisions_path, vault_path, [(written[0], "pearl"), (written[1], "keep"), (written[2], "sink")])

            with redirect_stdout(stdout):
                result = main(["plan-agent-finish", "--vault", str(vault_path), "--decisions", str(decisions_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["reviewed"], 3)
            self.assertEqual(data["summary"]["remaining"], 1)
            self.assertEqual(data["summary"]["pearls"], 1)
            self.assertEqual(data["summary"]["kept"], 1)
            self.assertEqual(data["summary"]["sunk"], 1)
            self.assertEqual(len(data["taste_examples"]["pearl"]), 1)
            self.assertEqual(len(data["taste_examples"]["keep"]), 1)
            self.assertEqual(len(data["taste_examples"]["sink"]), 1)
            self.assertEqual(len(data["remaining_drops"]), 1)
            self.assertTrue(data["agent_instructions"])
            self.assertIn("Created agent finish plan:", stdout.getvalue())

    def test_plan_agent_finish_default_output_path(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_plan_decisions(decisions_path, vault_path, [(written[0], "keep")])

            with redirect_stdout(stdout):
                result = main(["plan-agent-finish", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            outputs = list((vault_path / "MemoReef" / "agent-plans").glob("*-agent-finish-plan.json"))
            self.assertEqual(result, 0)
            self.assertEqual(len(outputs), 1)
            data = json.loads(outputs[0].read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["reviewed"], 1)
            self.assertEqual(data["summary"]["remaining"], 0)

    def test_plan_agent_finish_missing_and_malformed_decisions_warn(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            output_path = Path(tmp) / "agent-finish-plan.json"
            decisions_path = Path(tmp) / "decisions.json"
            payload = {
                "version": 1,
                "decisions": [
                    "bad item",
                    {"path": "MemoReef/Drops/missing.md", "decision": "keep"},
                    {"path": "MemoReef/Drops/also-missing.md", "decision": "strange"},
                ],
            }
            decisions_path.write_text(json.dumps(payload), encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["plan-agent-finish", "--vault", str(vault_path), "--decisions", str(decisions_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["reviewed"], 0)
            self.assertEqual(data["summary"]["remaining"], 1)
            self.assertEqual(len(data["warnings"]), 3)
            self.assertIn("- warnings: 3", stdout.getvalue())

    def test_plan_agent_finish_does_not_modify_markdown_drops(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")
            decisions_path = Path(tmp) / "decisions.json"
            output_path = Path(tmp) / "agent-finish-plan.json"
            self.write_plan_decisions(decisions_path, vault_path, [(written[0], "pearl")])

            with redirect_stdout(stdout):
                result = main(["plan-agent-finish", "--vault", str(vault_path), "--decisions", str(decisions_path), "--output", str(output_path)])

            self.assertEqual(result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)

    def write_plan(self, path: Path, remaining: object, taste_examples=None):
        path.write_text(
            json.dumps({"version": 1, "remaining_drops": remaining, "taste_examples": taste_examples or {"pearl": [], "keep": [], "sink": []}}),
            encoding="utf-8",
        )

    def test_draft_agent_proposals_explicit_output(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "agent-finish-plan.json"
            output_path = Path(tmp) / "agent-proposals.json"
            self.write_plan(plan_path, [{"id": "a", "path": "a.md", "title": "Local AI agents", "tags": ["ai-agents"], "status": "drift"}])

            with redirect_stdout(stdout):
                result = main(["draft-agent-proposals", "--plan", str(plan_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["proposed"], 1)
            self.assertIn("proposed_status", data["proposals"][0])
            self.assertIn("Drafted agent proposals:", stdout.getvalue())

    def test_draft_agent_proposals_default_output_path(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "agent-finish-plan.json"
            self.write_plan(plan_path, [{"id": "a", "path": "a.md", "title": "Local AI agents"}])

            with redirect_stdout(stdout):
                result = main(["draft-agent-proposals", "--plan", str(plan_path)])

            outputs = list(Path(tmp).glob("*-agent-proposals.json"))
            self.assertEqual(result, 0)
            self.assertEqual(len(outputs), 1)

    def test_draft_agent_proposals_pearl_sink_and_weak_rules(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "agent-finish-plan.json"
            output_path = Path(tmp) / "agent-proposals.json"
            taste = {
                "pearl": [{"title": "local ai agents research", "tags": ["ai-agents", "research"]}],
                "keep": [],
                "sink": [{"title": "coupon spam deals", "tags": ["spam", "coupons"]}],
            }
            remaining = [
                {"id": "p", "path": "p.md", "title": "local ai agents research", "tags": ["ai-agents", "research"], "status": "drift"},
                {"id": "s", "path": "s.md", "title": "coupon spam deals", "tags": ["spam", "coupons"], "status": "drift"},
                {"id": "w", "path": "w.md", "title": "unrelated orchard", "tags": ["keepme"], "status": "drift"},
            ]
            self.write_plan(plan_path, remaining, taste)

            with redirect_stdout(stdout):
                result = main(["draft-agent-proposals", "--plan", str(plan_path), "--output", str(output_path)])

            proposals = {item["id"]: item for item in json.loads(output_path.read_text(encoding="utf-8"))["proposals"]}
            self.assertEqual(result, 0)
            self.assertEqual(proposals["p"]["proposed_status"], "reef")
            self.assertEqual(proposals["p"]["proposed_pearl"], True)
            self.assertEqual(proposals["s"]["proposed_status"], "discarded")
            self.assertEqual(proposals["w"]["proposed_status"], "drift")
            self.assertEqual(proposals["w"]["confidence"], "low")
            self.assertEqual(proposals["w"]["requires_user_review"], True)
            self.assertEqual(proposals["w"]["suggested_tags"], ["keepme"])

    def test_draft_agent_proposals_malformed_remaining_warns_zero(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "agent-finish-plan.json"
            output_path = Path(tmp) / "agent-proposals.json"
            self.write_plan(plan_path, "not-a-list")

            with redirect_stdout(stdout):
                result = main(["draft-agent-proposals", "--plan", str(plan_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["proposed"], 0)
            self.assertEqual(len(data["warnings"]), 1)

    def test_draft_agent_proposals_does_not_modify_markdown(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Local AI agents", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")
            plan_path = Path(tmp) / "agent-finish-plan.json"
            output_path = Path(tmp) / "agent-proposals.json"
            self.write_plan(plan_path, [{"id": "a", "path": "a.md", "title": "Local AI agents"}])

            with redirect_stdout(stdout):
                result = main(["draft-agent-proposals", "--plan", str(plan_path), "--output", str(output_path)])

            self.assertEqual(result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)

    def test_app_command_creates_dashboard_with_counts(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Drift Source", "https://drift.example"),
                Bookmark("Pearl Source", "https://pearl.example", status="reef", pearl=True),
                Bookmark("Discarded Source", "https://discarded.example", status="discarded"),
            ], vault_path)

            with redirect_stdout(stdout):
                result = main(["app", "--vault", str(vault_path)])

            dashboard = vault_path / "MemoReef" / "app" / "index.html"
            tour = vault_path / "MemoReef" / "app" / "tour.html"
            review = vault_path / "MemoReef" / "app" / "review.html"
            reports = vault_path / "MemoReef" / "app" / "reports.html"
            briefs = vault_path / "MemoReef" / "app" / "briefs.html"
            html = dashboard.read_text(encoding="utf-8")
            tour_html = tour.read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertTrue(dashboard.exists())
            self.assertTrue(tour.exists())
            self.assertTrue(review.exists())
            self.assertTrue(reports.exists())
            self.assertTrue(briefs.exists())
            self.assertTrue(list((vault_path / "MemoReef" / "app" / "drops").glob("*.html")))
            self.assertIn("MemoReef local app", html)
            self.assertIn("tour.html", html)
            self.assertIn("review.html", html)
            self.assertIn("reports.html", html)
            self.assertIn("briefs.html", html)
            self.assertIn("Total Drops", html)
            self.assertIn("Drift", html)
            self.assertIn("Review Mode", html)
            self.assertIn("Agent proposals", html)
            self.assertIn("Why local Markdown matters", tour_html)
            self.assertIn("Messy saves become source memory", tour_html)
            self.assertIn("review.html", tour_html)
            self.assertIn("reports.html", tour_html)
            self.assertIn("briefs.html", tour_html)
            self.assertIn("Generated MemoReef app dashboard", stdout.getvalue())

    def test_app_command_handles_empty_vault(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "empty-vault"

            with redirect_stdout(stdout):
                result = main(["app", "--vault", str(vault_path)])

            dashboard = vault_path / "MemoReef" / "app" / "index.html"
            html = dashboard.read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("Import bookmarks", html)
            self.assertIn("Total Drops", html)

    def test_demo_command_creates_complete_demo_vault(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "memoreef-demo"

            with redirect_stdout(stdout):
                result = main(["demo", "--output", str(output_path)])

            root = output_path / "MemoReef"
            drops = sorted((root / "Drops").glob("*.md"))
            readme = root / "DEMO_README.md"
            dashboard = root / "app" / "index.html"
            library = root / "app" / "library.html"
            tour = root / "app" / "tour.html"
            review = root / "app" / "review.html"
            reports = root / "app" / "reports.html"
            app_briefs = root / "app" / "briefs.html"
            pilot = root / "app" / "pilot.html"
            detail_pages = list((root / "app" / "drops").glob("*.html"))
            review_sessions = list((root / "review-sessions").glob("*-review-session.json"))
            duplicate_reports = list((root / "reports").glob("*-duplicate-report.json"))
            garden_reports = list((root / "reports").glob("*-garden-suggestions.json"))
            search_results = list((root / "search").glob("*-search-results.json"))
            briefs = list((root / "briefs").glob("*project-brief.md"))
            agent_plans = list((root / "agent-plans").glob("*-agent-finish-plan.json"))
            agent_proposals = list((root / "agent-plans").glob("*-agent-proposals.json"))

            statuses = set()
            pearls = 0
            combined_text = ""
            for drop in drops:
                text = drop.read_text(encoding="utf-8")
                combined_text += text
                frontmatter, _body = parse_markdown_frontmatter(text)
                statuses.add(frontmatter.get("status"))
                if frontmatter.get("pearl") is True:
                    pearls += 1

            self.assertEqual(result, 0)
            self.assertGreaterEqual(len(drops), 12)
            self.assertTrue({"drift", "reef", "deep", "discarded"}.issubset(statuses))
            self.assertGreaterEqual(pearls, 2)
            self.assertTrue(readme.exists())
            self.assertTrue(dashboard.exists())
            self.assertTrue(library.exists())
            self.assertTrue(tour.exists())
            self.assertTrue(review.exists())
            self.assertTrue(reports.exists())
            self.assertTrue(app_briefs.exists())
            self.assertTrue(pilot.exists())
            self.assertTrue((root / "PILOT_README.md").exists())
            self.assertTrue(detail_pages)
            self.assertTrue(review_sessions)
            self.assertTrue(duplicate_reports)
            self.assertTrue(garden_reports)
            self.assertTrue(search_results)
            self.assertTrue(briefs)
            self.assertTrue(agent_plans)
            self.assertTrue(agent_proposals)
            self.assertTrue((output_path / "memoreef-demo-review-decisions.json").exists())
            self.assertIn("projects:", combined_text)
            self.assertIn("shoals:", combined_text)
            self.assertIn("tags:", combined_text)
            self.assertIn("hostname:", combined_text)
            self.assertIn("page_title:", combined_text)
            self.assertIn("Created MemoReef demo vault:", stdout.getvalue())
            readme_text = readme.read_text(encoding="utf-8")
            tour_html = tour.read_text(encoding="utf-8")
            self.assertIn("app/tour.html", readme_text)
            self.assertIn("app/pilot.html", readme_text)
            self.assertIn("app/review.html", readme_text)
            self.assertIn("app/reports.html", readme_text)
            self.assertIn("app/briefs.html", readme_text)
            self.assertIn("what problem this solves", readme_text.lower())
            self.assertIn("Library/Search", library.read_text(encoding="utf-8"))
            self.assertIn("Review Mode", review.read_text(encoding="utf-8"))
            self.assertIn("duplicate report", reports.read_text(encoding="utf-8").lower())
            self.assertIn("project brief", app_briefs.read_text(encoding="utf-8").lower())
            brief_text = briefs[0].read_text(encoding="utf-8")
            self.assertIn("Local AI agent playbook for research teams", brief_text)
            self.assertIn("Agent handoff", brief_text)
            self.assertIn("project brief", readme_text)
            self.assertIn("Pilot checklist", pilot.read_text(encoding="utf-8"))
            self.assertIn("Why local Markdown matters", tour_html)
            self.assertIn("Local AI agent playbook for research teams", tour_html)
            self.assertTrue(any("Local AI agent playbook for research teams" in path.read_text(encoding="utf-8") for path in detail_pages))

    def test_generated_app_pages_do_not_use_external_assets_or_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("Offline Source", "https://offline.example")], vault_path)

            with redirect_stdout(io.StringIO()):
                result = main(["app", "--vault", str(vault_path)])

            self.assertEqual(result, 0)
            app_dir = vault_path / "MemoReef" / "app"
            for page in app_dir.rglob("*.html"):
                html = page.read_text(encoding="utf-8").lower()
                self.assertNotIn("<script", html)
                self.assertNotIn("rel=\"stylesheet\"", html)
                self.assertNotIn("<link", html)
                self.assertNotIn("<script src=", html)
                self.assertNotIn("@import", html)
                self.assertNotIn("url(", html)
                self.assertNotIn("cdn", html)
                if "/drops/" not in page.as_posix():
                    self.assertNotIn("https://", html)
                    self.assertNotIn("http://", html)

    def test_landing_page_redirect_points_to_current_public_site(self):
        repo_root = Path(__file__).parent.parent
        html = (repo_root / "site" / "index.html").read_text(encoding="utf-8")
        lowered = html.lower()

        self.assertIn("save sources", lowered)
        self.assertIn("let ideas surface", lowered)
        self.assertIn("https://memoreef.de/", lowered)
        self.assertIn("rel=\"canonical\"", lowered)
        self.assertNotIn("memoreef-octopus-abyss.jpg", lowered)
        self.assertNotIn("memoreef-octopus-pearl.jpg", lowered)
        self.assertNotIn("<script src=", lowered)
        self.assertNotIn("cdn", lowered)

    def test_app_command_detects_existing_review_and_proposal_files(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            (vault_path / "MemoReef" / "review-sessions").mkdir(parents=True)
            (vault_path / "MemoReef" / "agent-plans").mkdir(parents=True)
            (vault_path / "MemoReef" / "review-sessions" / "2026-06-12-120000-review-session.json").write_text("{}", encoding="utf-8")
            (vault_path / "memoreef-review-decisions.json").write_text("{}", encoding="utf-8")
            (vault_path / "MemoReef" / "agent-plans" / "2026-06-12-121000-agent-finish-plan.json").write_text("{}", encoding="utf-8")
            (vault_path / "MemoReef" / "agent-plans" / "2026-06-12-122000-agent-proposals.json").write_text("{}", encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("MemoReef/review-sessions/2026-06-12-120000-review-session.json", html)
            self.assertIn("memoreef-review-decisions.json", html)
            self.assertIn("2026-06-12-121000-agent-finish-plan.json", html)
            self.assertIn("2026-06-12-122000-agent-proposals.json", html)

    def test_app_and_tour_detect_latest_project_brief(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            brief_dir = vault_path / "MemoReef" / "briefs"
            brief_dir.mkdir(parents=True)
            (brief_dir / "2026-06-12-120000-ai-agents-project-brief.md").write_text("# Old Brief\n", encoding="utf-8")
            (brief_dir / "2026-06-12-121000-ai-agents-project-brief.md").write_text("# Latest Brief\n", encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["app", "--vault", str(vault_path)])

            dashboard = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            tour = (vault_path / "MemoReef" / "app" / "tour.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("MemoReef/briefs/2026-06-12-121000-ai-agents-project-brief.md", dashboard)
            self.assertNotIn("MemoReef/briefs/2026-06-12-120000-ai-agents-project-brief.md", dashboard)
            self.assertIn("Latest project brief Markdown", tour)
            self.assertIn("2026-06-12-121000-ai-agents-project-brief.md", tour)

    def write_proposals(self, path: Path, vault_path: Path, proposals):
        normalized = []
        for drop_path, status, pearl, requires_review, extra in proposals:
            item = {
                "id": str(drop_path.resolve().relative_to(vault_path.resolve())),
                "path": str(drop_path.resolve().relative_to(vault_path.resolve())),
                "proposed_status": status,
                "proposed_pearl": pearl,
                "confidence": extra.get("confidence", "high"),
                "priority": extra.get("priority", "normal"),
                "suggested_note_location": extra.get("suggested_note_location", "MemoReef/Reef"),
                "suggested_tags": extra.get("suggested_tags", ["ignored"]),
                "requires_user_review": requires_review,
            }
            normalized.append(item)
        path.write_text(json.dumps({"version": 1, "proposals": normalized}), encoding="utf-8")

    def test_apply_agent_proposals_updates_frontmatter(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example", "https://example.com", tags=["original"], folders=["Inbox"])], vault_path)
            proposals_path = Path(tmp) / "agent-proposals.json"
            self.write_proposals(proposals_path, vault_path, [(written[0], "reef", False, False, {"priority": "normal", "suggested_note_location": "MemoReef/Reef", "confidence": "high", "suggested_tags": ["new-tag"]})])

            with redirect_stdout(stdout):
                result = main(["apply-agent-proposals", "--vault", str(vault_path), "--proposals", str(proposals_path)])

            text = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("status: reef", text)
            self.assertIn("pearl: false", text)
            self.assertIn('priority: "normal"', text)
            self.assertIn('note_location: "MemoReef/Reef"', text)
            self.assertIn("agent_proposed_at:", text)
            self.assertIn('agent_confidence: "high"', text)
            self.assertIn('  - "original"', text)
            self.assertNotIn("new-tag", text)
            self.assertIn("# Example", text)

    def test_apply_agent_proposals_pearl_and_discarded(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Pearl", "https://pearl.example"), Bookmark("Noise", "https://noise.example")], vault_path)
            proposals_path = Path(tmp) / "agent-proposals.json"
            self.write_proposals(proposals_path, vault_path, [
                (written[0], "reef", True, False, {"priority": "high", "suggested_note_location": "MemoReef/Pearls"}),
                (written[1], "discarded", False, False, {"priority": "low", "suggested_note_location": "MemoReef/Discarded"}),
            ])

            with redirect_stdout(stdout):
                result = main(["apply-agent-proposals", "--vault", str(vault_path), "--proposals", str(proposals_path)])

            self.assertEqual(result, 0)
            self.assertIn("status: reef", written[0].read_text(encoding="utf-8"))
            self.assertIn("pearl: true", written[0].read_text(encoding="utf-8"))
            self.assertIn("status: discarded", written[1].read_text(encoding="utf-8"))
            self.assertIn("pearl: false", written[1].read_text(encoding="utf-8"))

    def test_apply_agent_proposals_dry_run_and_needs_review(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Review", "https://review.example")], vault_path)
            before = written[0].read_text(encoding="utf-8")
            proposals_path = Path(tmp) / "agent-proposals.json"
            self.write_proposals(proposals_path, vault_path, [(written[0], "reef", False, True, {})])

            with redirect_stdout(stdout):
                dry_result = main(["apply-agent-proposals", "--vault", str(vault_path), "--proposals", str(proposals_path), "--dry-run", "--include-needs-review"])
            self.assertEqual(dry_result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)
            self.assertIn("Dry run agent proposals", stdout.getvalue())

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                skipped_result = main(["apply-agent-proposals", "--vault", str(vault_path), "--proposals", str(proposals_path)])
            self.assertEqual(skipped_result, 0)
            self.assertIn("- skipped: 1", stdout.getvalue())
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)

            with redirect_stdout(io.StringIO()):
                applied_result = main(["apply-agent-proposals", "--vault", str(vault_path), "--proposals", str(proposals_path), "--include-needs-review"])
            self.assertEqual(applied_result, 0)
            self.assertIn("status: reef", written[0].read_text(encoding="utf-8"))

    def test_apply_agent_proposals_missing_traversal_and_invalid_status_warn(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            outside = Path(tmp) / "outside.md"
            outside.write_text("outside", encoding="utf-8")
            written = write_bookmarks_to_vault([Bookmark("Bad", "https://bad.example")], vault_path)
            before = outside.read_text(encoding="utf-8")
            proposals_path = Path(tmp) / "agent-proposals.json"
            payload = {
                "version": 1,
                "proposals": [
                    {"path": "MemoReef/Drops/missing.md", "proposed_status": "reef", "proposed_pearl": False, "requires_user_review": False},
                    {"path": "../outside.md", "proposed_status": "reef", "proposed_pearl": False, "requires_user_review": False},
                    {"path": str(written[0].resolve().relative_to(vault_path.resolve())), "proposed_status": "bogus", "proposed_pearl": False, "requires_user_review": False},
                ],
            }
            proposals_path.write_text(json.dumps(payload), encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["apply-agent-proposals", "--vault", str(vault_path), "--proposals", str(proposals_path)])

            self.assertEqual(result, 0)
            self.assertEqual(outside.read_text(encoding="utf-8"), before)
            output = stdout.getvalue()
            self.assertIn("- skipped: 3", output)
            self.assertIn("file not found", output)
            self.assertIn("outside the vault", output)
            self.assertIn("unsupported proposed_status", output)

    def test_duplicate_report_explicit_output_groups_urls_and_domains(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "duplicate-report.json"
            write_bookmarks_to_vault([
                Bookmark("Example Article", "https://example.com/article?utm_source=test"),
                Bookmark("Example Article Copy", "https://example.com/article"),
                Bookmark("Other Example", "https://example.com/other"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(stdout):
                result = main(["duplicate-report", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["total_drops"], 3)
            self.assertEqual(data["summary"]["exact_url_groups"], 1)
            self.assertEqual(data["summary"]["same_domain_groups"], 1)
            self.assertIn("Created duplicate report", stdout.getvalue())

    def test_duplicate_report_default_output_and_similar_titles(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Local AI Agents Small Teams Guide", "https://a.example/one"),
                Bookmark("Local AI Agents Small Teams Handbook", "https://b.example/two"),
                Bookmark("Completely Different Orchard", "https://c.example/three"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(stdout):
                result = main(["duplicate-report", "--vault", str(vault_path)])

            reports = list((vault_path / "MemoReef" / "reports").glob("*-duplicate-report.json"))
            self.assertEqual(result, 0)
            self.assertEqual(len(reports), 1)
            data = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertGreaterEqual(data["summary"]["similar_title_groups"], 1)
            self.assertEqual(data["summary"]["exact_url_groups"], 0)

    def test_duplicate_report_does_not_modify_markdown_and_dashboard_detects_it(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["duplicate-report", "--vault", str(vault_path)])
            with redirect_stdout(io.StringIO()):
                app_result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertEqual(app_result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)
            self.assertIn("Duplicate report", html)
            self.assertIn("duplicate-report", html)

    def test_check_links_explicit_output_writes_report(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            write_bookmarks_to_vault([Bookmark("Example", "https://example.com")], vault_path)

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200)):
                with redirect_stdout(stdout):
                    result = main(["check-links", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["summary"]["checked"], 1)
            self.assertEqual(data["results"][0]["status"], "ok")
            self.assertIn("Created link check report", stdout.getvalue())

    def test_check_links_default_output_under_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([Bookmark("Example", "https://example.com")], vault_path)

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200)):
                with redirect_stdout(io.StringIO()):
                    result = main(["check-links", "--vault", str(vault_path)])

            reports = list((vault_path / "MemoReef" / "reports").glob("*-link-check-report.json"))
            self.assertEqual(result, 0)
            self.assertEqual(len(reports), 1)

    def test_check_links_classifies_http_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            write_bookmarks_to_vault([
                Bookmark("OK", "https://ok.example"),
                Bookmark("Missing", "https://missing.example"),
                Bookmark("Forbidden", "https://forbidden.example"),
            ], vault_path, allow_duplicates=True)

            def fake_urlopen(request, timeout=5):
                url = request.full_url
                if "missing" in url:
                    raise urllib.error.HTTPError(url, 404, "missing", {}, io.BytesIO())
                if "forbidden" in url:
                    raise urllib.error.HTTPError(url, 403, "forbidden", {}, io.BytesIO())
                return FakeHTTPResponse(200, url)

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=fake_urlopen):
                with redirect_stdout(io.StringIO()):
                    result = main([
                        "check-links",
                        "--vault",
                        str(vault_path),
                        "--output",
                        str(output_path),
                        "--method",
                        "head",
                    ])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            statuses = {item["title"]: item["status"] for item in data["results"]}
            self.assertEqual(result, 0)
            self.assertEqual(statuses["OK"], "ok")
            self.assertEqual(statuses["Missing"], "broken")
            self.assertEqual(statuses["Forbidden"], "suspicious")

    def test_check_links_timeout_and_unsupported_url_are_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            write_bookmarks_to_vault([
                Bookmark("Timeout", "https://timeout.example"),
                Bookmark("FTP", "ftp://example.com/file"),
            ], vault_path, allow_duplicates=True)

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=TimeoutError("timed out")) as mocked:
                with redirect_stdout(io.StringIO()):
                    result = main(["check-links", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            statuses = {item["title"]: item["status"] for item in data["results"]}
            self.assertEqual(result, 0)
            self.assertEqual(statuses["Timeout"], "unknown")
            self.assertEqual(statuses["FTP"], "unknown")
            self.assertEqual(mocked.call_count, 2)

    def test_check_links_limit_checks_only_first_n_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            write_bookmarks_to_vault([
                Bookmark("One", "https://one.example"),
                Bookmark("Two", "https://two.example"),
                Bookmark("Three", "https://three.example"),
            ], vault_path, allow_duplicates=True)

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200)) as mocked:
                with redirect_stdout(io.StringIO()):
                    result = main([
                        "check-links",
                        "--vault",
                        str(vault_path),
                        "--output",
                        str(output_path),
                        "--limit",
                        "2",
                    ])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["total_drops"], 2)
            self.assertEqual(data["summary"]["checked"], 2)
            self.assertEqual(mocked.call_count, 2)

    def test_check_links_head_does_not_fallback_to_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            write_bookmarks_to_vault([Bookmark("Method", "https://method.example")], vault_path)

            def fake_urlopen(request, timeout=5):
                self.assertEqual(request.get_method(), "HEAD")
                raise urllib.error.HTTPError(request.full_url, 405, "no head", {}, io.BytesIO())

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=fake_urlopen) as mocked:
                with redirect_stdout(io.StringIO()):
                    result = main([
                        "check-links",
                        "--vault",
                        str(vault_path),
                        "--output",
                        str(output_path),
                        "--method",
                        "head",
                    ])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(mocked.call_count, 1)
            self.assertEqual(data["results"][0]["method"], "HEAD")

    def test_check_links_auto_falls_back_from_head_405_to_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            write_bookmarks_to_vault([Bookmark("Fallback", "https://fallback.example")], vault_path)
            methods = []

            def fake_urlopen(request, timeout=5):
                methods.append(request.get_method())
                if request.get_method() == "HEAD":
                    raise urllib.error.HTTPError(request.full_url, 405, "no head", {}, io.BytesIO())
                return FakeHTTPResponse(200, request.full_url)

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=fake_urlopen):
                with redirect_stdout(io.StringIO()):
                    result = main(["check-links", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(methods, ["HEAD", "GET"])
            self.assertEqual(data["results"][0]["status"], "ok")
            self.assertEqual(data["results"][0]["method"], "GET")

    def test_check_links_skips_empty_urls_and_does_not_modify_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "link-check-report.json"
            written = write_bookmarks_to_vault([
                Bookmark("Empty", ""),
                Bookmark("Good", "https://good.example"),
            ], vault_path, allow_duplicates=True)
            before = {path: path.read_text(encoding="utf-8") for path in written}

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200)):
                with redirect_stdout(io.StringIO()):
                    result = main(["check-links", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["summary"]["checked"], 1)
            self.assertEqual(data["summary"]["skipped"], 1)
            self.assertTrue(data["warnings"])
            self.assertEqual({path: path.read_text(encoding="utf-8") for path in written}, before)

    def test_app_command_detects_existing_link_check_report(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            (vault_path / "MemoReef" / "reports").mkdir(parents=True)
            (vault_path / "MemoReef" / "reports" / "2026-06-12-150000-link-check-report.json").write_text("{}", encoding="utf-8")

            with redirect_stdout(stdout):
                result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("Link check report", html)
            self.assertIn("link-check-report", html)

    def test_refresh_metadata_updates_frontmatter(self):
        html = b"""<!doctype html>
<html><head>
<title>Fallback Title</title>
<meta name="description" content="Fallback description">
<meta property="og:title" content="OG Title">
<meta property="og:description" content="OG description">
<link rel="canonical" href="/canonical?utm_source=test">
</head><body>hello</body></html>"""
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Old", "https://example.com/page")], vault_path)

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200, "https://example.com/final", html, "utf-8")) as mocked:
                with redirect_stdout(stdout):
                    result = main(["refresh-metadata", "--vault", str(vault_path)])

            text = written[0].read_text(encoding="utf-8")
            request = mocked.call_args.args[0]
            self.assertEqual(result, 0)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.headers["User-agent"], "MemoReef/0.1 local metadata refresh")
            self.assertIn('page_title: "OG Title"', text)
            self.assertIn('page_description: "OG description"', text)
            self.assertIn('canonical_url: "https://example.com/canonical"', text)
            self.assertIn('hostname: "example.com"', text)
            self.assertIn("metadata_refreshed_at:", text)
            self.assertIn('metadata_status: "ok"', text)
            self.assertIn('metadata_error: ""', text)
            self.assertIn("# Old", text)
            self.assertIn("Refreshed metadata:", stdout.getvalue())
            self.assertIn("- updated: 1", stdout.getvalue())
            self.assertIn("- skipped: 0", stdout.getvalue())
            self.assertIn("- warnings: 0", stdout.getvalue())

    def test_refresh_metadata_extracts_title_and_meta_description(self):
        html = b"""<!doctype html>
<html><head>
<title>Plain Title</title>
<meta name="description" content="Plain description.">
</head><body>hello</body></html>"""
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Old", "https://example.com/plain")], vault_path)

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200, "https://example.com/plain", html, "utf-8")):
                with redirect_stdout(io.StringIO()):
                    result = main(["refresh-metadata", "--vault", str(vault_path)])

            text = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn('page_title: "Plain Title"', text)
            self.assertIn('page_description: "Plain description."', text)

    def test_refresh_metadata_dry_run_does_not_modify_markdown(self):
        html = b"<html><head><title>New Title</title></head></html>"
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Old", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200, "https://example.com", html)):
                with redirect_stdout(stdout):
                    result = main(["refresh-metadata", "--vault", str(vault_path), "--dry-run"])

            self.assertEqual(result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)
            self.assertIn("Dry run metadata refresh:", stdout.getvalue())
            self.assertIn("- would update: 1", stdout.getvalue())
            self.assertIn("- skipped: 0", stdout.getvalue())
            self.assertIn("- warnings: 0", stdout.getvalue())
            self.assertIn("- would update files:", stdout.getvalue())

    def test_refresh_metadata_limit_only_fetches_first_n_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("One", "https://one.example"),
                Bookmark("Two", "https://two.example"),
                Bookmark("Three", "https://three.example"),
            ], vault_path, allow_duplicates=True)

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200, "https://example.com", b"<title>x</title>")) as mocked:
                with redirect_stdout(io.StringIO()):
                    result = main(["refresh-metadata", "--vault", str(vault_path), "--limit", "2"])

            self.assertEqual(result, 0)
            self.assertEqual(mocked.call_count, 2)

    def test_refresh_metadata_unknown_url_and_network_error(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("FTP", "ftp://example.com/file"),
                Bookmark("Timeout", "https://timeout.example"),
            ], vault_path, allow_duplicates=True)

            with patch("memoreef.cli.urllib.request.urlopen", side_effect=TimeoutError("timed out")) as mocked:
                with redirect_stdout(stdout):
                    result = main(["refresh-metadata", "--vault", str(vault_path)])

            texts = "\n".join(path.read_text(encoding="utf-8") for path in written)
            self.assertEqual(result, 0)
            self.assertEqual(mocked.call_count, 1)
            self.assertIn('metadata_status: "unknown"', texts)
            self.assertIn('metadata_error: "unsupported URL scheme"', texts)
            self.assertIn('metadata_error: "timed out"', texts)
            self.assertIn("- warnings: 2", stdout.getvalue())

    def test_refresh_metadata_preserves_existing_fields_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark(
                    "Keep Me",
                    "https://example.com",
                    folders=["Research"],
                    tags=["original"],
                    projects=["Project A"],
                    shoals=["Shoal A"],
                )
            ], vault_path)
            before_body_marker = "## Notes"

            with patch("memoreef.cli.urllib.request.urlopen", return_value=FakeHTTPResponse(200, "https://example.com", b"<title>Page</title>")):
                with redirect_stdout(io.StringIO()):
                    result = main(["refresh-metadata", "--vault", str(vault_path)])

            text = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn('title: "Keep Me"', text)
            self.assertIn('url: "https://example.com"', text)
            self.assertIn('  - "Research"', text)
            self.assertIn('  - "original"', text)
            self.assertIn('  - "Project A"', text)
            self.assertIn('  - "Shoal A"', text)
            self.assertIn(before_body_marker, text)

    def test_app_workflow_mentions_refresh_metadata(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"

            with redirect_stdout(stdout):
                result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("refresh-metadata", html)

    def test_suggest_gardens_explicit_output_suggests_project_and_shoal(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "garden-suggestions.json"
            write_bookmarks_to_vault([
                Bookmark(
                    "Agent automation patterns",
                    "https://example.com/agent-automation",
                    folders=["AI"],
                    tags=["agents"],
                    projects=["AI Agents"],
                    shoals=["Automation"],
                    status="reef",
                    pearl=True,
                ),
                Bookmark("Agent automation workflows", "https://example.com/agent-workflows", folders=["AI"], tags=["agents"]),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(stdout):
                result = main(["suggest-gardens", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            suggestion = data["suggestions"][0]
            self.assertEqual(result, 0)
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["summary"]["example_drops"], 1)
            self.assertEqual(data["summary"]["candidate_drops"], 1)
            self.assertEqual(suggestion["suggested_projects"][0]["name"], "AI Agents")
            self.assertEqual(suggestion["suggested_shoals"][0]["name"], "Automation")
            self.assertTrue(suggestion["suggested_projects"][0]["evidence_tokens"])
            self.assertTrue(suggestion["suggested_projects"][0]["source_examples"])
            self.assertIn("Created garden suggestions:", stdout.getvalue())

    def test_suggest_gardens_default_output_under_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Design systems", "https://design.example/system", projects=["Design"]),
                Bookmark("Design system checklist", "https://design.example/checklist"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(io.StringIO()):
                result = main(["suggest-gardens", "--vault", str(vault_path)])

            reports = list((vault_path / "MemoReef" / "reports").glob("*-garden-suggestions.json"))
            self.assertEqual(result, 0)
            self.assertEqual(len(reports), 1)

    def test_suggest_gardens_no_examples_warns(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "garden-suggestions.json"
            write_bookmarks_to_vault([Bookmark("Loose", "https://loose.example")], vault_path)

            with redirect_stdout(stdout):
                result = main(["suggest-gardens", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(data["suggestions"], [])
            self.assertEqual(data["summary"]["warnings"], 1)
            self.assertIn("No Drops with projects or shoals found", data["warnings"][0])
            self.assertIn("- warnings: 1", stdout.getvalue())

    def test_suggest_gardens_respects_existing_project_or_shoal_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "garden-suggestions.json"
            write_bookmarks_to_vault([
                Bookmark("Agent automation source", "https://example.com/source", tags=["agents"], projects=["AI Agents"], shoals=["Automation"]),
                Bookmark("Agent automation has project", "https://example.com/project", tags=["agents"], projects=["Manual Project"]),
                Bookmark("Agent automation has shoal", "https://example.com/shoal", tags=["agents"], shoals=["Manual Shoal"]),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(io.StringIO()):
                result = main(["suggest-gardens", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            by_title = {item["title"]: item for item in data["suggestions"]}
            self.assertEqual(result, 0)
            self.assertEqual(by_title["Agent automation has project"]["suggested_projects"], [])
            self.assertTrue(by_title["Agent automation has project"]["suggested_shoals"])
            self.assertTrue(by_title["Agent automation has shoal"]["suggested_projects"])
            self.assertEqual(by_title["Agent automation has shoal"]["suggested_shoals"], [])

    def test_suggest_gardens_deterministic_sort_order_for_equal_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            output_path = Path(tmp) / "garden-suggestions.json"
            write_bookmarks_to_vault([
                Bookmark("Shared research topic", "https://alpha.example/source", tags=["shared"], projects=["Alpha"]),
                Bookmark("Shared research topic", "https://beta.example/source", tags=["shared"], projects=["Beta"]),
                Bookmark("Shared research topic", "https://candidate.example/item", tags=["shared"]),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(io.StringIO()):
                result = main(["suggest-gardens", "--vault", str(vault_path), "--output", str(output_path)])

            data = json.loads(output_path.read_text(encoding="utf-8"))
            names = [item["name"] for item in data["suggestions"][0]["suggested_projects"]]
            self.assertEqual(result, 0)
            self.assertEqual(names[:2], ["Alpha", "Beta"])

    def test_suggest_gardens_does_not_modify_markdown_and_dashboard_detects_report(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Agent automation source", "https://example.com/source", projects=["AI Agents"]),
                Bookmark("Agent automation candidate", "https://example.com/candidate"),
            ], vault_path, allow_duplicates=True)
            before = {path: path.read_text(encoding="utf-8") for path in written}

            with redirect_stdout(stdout):
                result = main(["suggest-gardens", "--vault", str(vault_path)])
            with redirect_stdout(io.StringIO()):
                app_result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertEqual(app_result, 0)
            self.assertEqual({path: path.read_text(encoding="utf-8") for path in written}, before)
            self.assertIn("Garden suggestions", html)
            self.assertIn("garden-suggestions", html)
            self.assertIn("suggest-gardens", html)

    def test_readme_and_tasks_mention_suggest_gardens(self):
        readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        tasks = (Path(__file__).parent.parent / "docs" / "CODEX_TASKS.md").read_text(encoding="utf-8")

        self.assertIn("suggest-gardens", readme)
        self.assertIn("Task 17", tasks)
        self.assertIn("suggest-gardens", tasks)

    def write_garden_suggestions(self, path: Path, vault_path: Path, items):
        suggestions = []
        for drop_path, projects, shoals in items:
            relative = drop_path.resolve().relative_to(vault_path.resolve()).as_posix()
            suggestions.append(
                {
                    "id": relative,
                    "path": relative,
                    "title": drop_path.stem,
                    "url": "https://example.com",
                    "suggested_projects": [{"name": name, "score": 4, "evidence_tokens": ["agent"], "source_examples": []} for name in projects],
                    "suggested_shoals": [{"name": name, "score": 4, "evidence_tokens": ["agent"], "source_examples": []} for name in shoals],
                }
            )
        path.write_text(json.dumps({"version": 1, "suggestions": suggestions}), encoding="utf-8")

    def test_apply_garden_suggestions_accept_all_applies_projects_and_shoals(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Candidate", "https://example.com")], vault_path)
            suggestions_path = Path(tmp) / "garden-suggestions.json"
            self.write_garden_suggestions(suggestions_path, vault_path, [(written[0], ["AI Agents"], ["Automation"])])

            with redirect_stdout(stdout):
                result = main(["apply-garden-suggestions", "--vault", str(vault_path), "--suggestions", str(suggestions_path), "--accept-all"])

            text = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn('  - "AI Agents"', text)
            self.assertIn('  - "Automation"', text)
            self.assertIn("Applied garden suggestions:", stdout.getvalue())
            self.assertIn("- files updated: 1", stdout.getvalue())
            self.assertIn("- projects added: 1", stdout.getvalue())
            self.assertIn("- shoals added: 1", stdout.getvalue())

    def test_apply_garden_suggestions_dry_run_does_not_modify_markdown(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Candidate", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")
            suggestions_path = Path(tmp) / "garden-suggestions.json"
            self.write_garden_suggestions(suggestions_path, vault_path, [(written[0], ["AI Agents"], ["Automation"])])

            with redirect_stdout(stdout):
                result = main(["apply-garden-suggestions", "--vault", str(vault_path), "--suggestions", str(suggestions_path), "--dry-run", "--accept-all"])

            self.assertEqual(result, 0)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)
            self.assertIn("Dry run garden suggestions:", stdout.getvalue())
            self.assertIn("- files that would update: 1", stdout.getvalue())
            self.assertIn("- projects that would be added: 1", stdout.getvalue())
            self.assertIn("- shoals that would be added: 1", stdout.getvalue())

    def test_apply_garden_suggestions_selective_project_and_shoal(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Project Candidate", "https://project.example"),
                Bookmark("Shoal Candidate", "https://shoal.example"),
            ], vault_path, allow_duplicates=True)
            project_suggestions = Path(tmp) / "project-suggestions.json"
            shoal_suggestions = Path(tmp) / "shoal-suggestions.json"
            self.write_garden_suggestions(project_suggestions, vault_path, [(written[0], ["AI Agents", "Design"], ["Automation"])])
            self.write_garden_suggestions(shoal_suggestions, vault_path, [(written[1], ["AI Agents"], ["Automation", "Research"])])

            with redirect_stdout(io.StringIO()):
                project_result = main([
                    "apply-garden-suggestions",
                    "--vault",
                    str(vault_path),
                    "--suggestions",
                    str(project_suggestions),
                    "--accept-project",
                    "AI Agents",
                ])
            with redirect_stdout(io.StringIO()):
                shoal_result = main([
                    "apply-garden-suggestions",
                    "--vault",
                    str(vault_path),
                    "--suggestions",
                    str(shoal_suggestions),
                    "--accept-shoal",
                    "Automation",
                ])

            project_text = written[0].read_text(encoding="utf-8")
            shoal_text = written[1].read_text(encoding="utf-8")
            self.assertEqual(project_result, 0)
            self.assertEqual(shoal_result, 0)
            self.assertIn('  - "AI Agents"', project_text)
            self.assertNotIn('  - "Design"', project_text)
            self.assertNotIn('  - "Automation"', project_text)
            self.assertIn('  - "Automation"', shoal_text)
            self.assertNotIn('  - "Research"', shoal_text)
            self.assertNotIn('  - "AI Agents"', shoal_text)

    def test_apply_garden_suggestions_does_not_duplicate_existing_labels(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Candidate", "https://example.com", projects=["AI Agents"], shoals=["Automation"])], vault_path)
            suggestions_path = Path(tmp) / "garden-suggestions.json"
            self.write_garden_suggestions(suggestions_path, vault_path, [(written[0], ["AI Agents"], ["Automation"])])

            with redirect_stdout(stdout):
                result = main(["apply-garden-suggestions", "--vault", str(vault_path), "--suggestions", str(suggestions_path), "--accept-all"])

            text = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertEqual(text.count('  - "AI Agents"'), 1)
            self.assertEqual(text.count('  - "Automation"'), 1)
            self.assertIn("- files updated: 0", stdout.getvalue())

    def test_apply_garden_suggestions_preserves_frontmatter_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Candidate", "https://example.com", folders=["Research"], tags=["original"], status="reef", pearl=True)
            ], vault_path)
            suggestions_path = Path(tmp) / "garden-suggestions.json"
            self.write_garden_suggestions(suggestions_path, vault_path, [(written[0], ["AI Agents"], ["Automation"])])

            with redirect_stdout(io.StringIO()):
                result = main(["apply-garden-suggestions", "--vault", str(vault_path), "--suggestions", str(suggestions_path), "--accept-all"])

            text = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn('title: "Candidate"', text)
            self.assertIn('url: "https://example.com"', text)
            self.assertIn("status: reef", text)
            self.assertIn("pearl: true", text)
            self.assertIn('  - "Research"', text)
            self.assertIn('  - "original"', text)
            self.assertIn("## Notes", text)

    def test_apply_garden_suggestions_missing_path_and_unmatched_label_warn(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            suggestions_path = Path(tmp) / "garden-suggestions.json"
            payload = {
                "version": 1,
                "suggestions": [
                    {
                        "path": "MemoReef/Drops/missing.md",
                        "suggested_projects": [{"name": "AI Agents"}],
                        "suggested_shoals": [{"name": "Automation"}],
                    }
                ],
            }
            suggestions_path.write_text(json.dumps(payload), encoding="utf-8")

            with redirect_stdout(stdout):
                result = main([
                    "apply-garden-suggestions",
                    "--vault",
                    str(vault_path),
                    "--suggestions",
                    str(suggestions_path),
                    "--accept-project",
                    "Nope",
                ])

            self.assertEqual(result, 0)
            output = stdout.getvalue()
            self.assertIn("- warnings: 2", output)
            self.assertIn('project "Nope" not present', output)
            self.assertIn("file not found", output)

    def test_apply_garden_suggestions_requires_accept_option(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Candidate", "https://example.com")], vault_path)
            before = written[0].read_text(encoding="utf-8")
            suggestions_path = Path(tmp) / "garden-suggestions.json"
            self.write_garden_suggestions(suggestions_path, vault_path, [(written[0], ["AI Agents"], ["Automation"])])

            with redirect_stdout(stdout):
                result = main(["apply-garden-suggestions", "--vault", str(vault_path), "--suggestions", str(suggestions_path)])

            self.assertEqual(result, 1)
            self.assertEqual(written[0].read_text(encoding="utf-8"), before)
            self.assertIn("No garden suggestion accept option provided", stdout.getvalue())

    def test_app_workflow_mentions_apply_garden_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"

            with redirect_stdout(io.StringIO()):
                result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("apply-garden-suggestions", html)

    def test_readme_and_tasks_mention_apply_garden_suggestions(self):
        readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        tasks = (Path(__file__).parent.parent / "docs" / "CODEX_TASKS.md").read_text(encoding="utf-8")

        self.assertIn("apply-garden-suggestions", readme)
        self.assertIn("Task 18", tasks)
        self.assertIn("apply-garden-suggestions", tasks)

    def test_hub_map_creates_index_hub_notes_and_drop_connections(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("AR art installation", "https://studio.example/ar-art", tags=["art", "augmented-reality"], projects=["Augmented Reality"], status="reef"),
                Bookmark("Gallery AR research", "https://gallery.example/ar", tags=["art", "augmented-reality"], projects=["Augmented Reality"], status="deep"),
                Bookmark("Discarded AR noise", "https://noise.example/ar", tags=["art", "augmented-reality"], status="discarded"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(stdout):
                result = main(["hub-map", "--vault", str(vault_path), "--min-drops", "2"])

            maps_dir = vault_path / "MemoReef" / "Maps"
            index = maps_dir / "Emerging Hubs.md"
            hub = maps_dir / "Hub - Augmented Reality.md"
            first_drop = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertTrue(index.exists())
            self.assertTrue(hub.exists())
            self.assertIn("[[MemoReef/Maps/Hub - Augmented Reality|Augmented Reality]]", index.read_text(encoding="utf-8"))
            self.assertIn("[[MemoReef/Drops/ar-art-installation|AR art installation]]", hub.read_text(encoding="utf-8"))
            self.assertIn("## MemoReef Connections", first_drop)
            self.assertIn("[[MemoReef/Maps/Hub - Art|Art]]", first_drop)
            self.assertIn("[[MemoReef/Maps/Hub - Augmented Reality|Augmented Reality]]", first_drop)
            self.assertNotIn("MemoReef Connections", written[2].read_text(encoding="utf-8"))
            self.assertIn("Created hub map:", stdout.getvalue())

    def test_hub_map_dry_run_does_not_modify_files(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Agent one", "https://example.com/one", tags=["ai-agents"], status="reef"),
                Bookmark("Agent two", "https://example.com/two", tags=["ai-agents"], status="reef"),
            ], vault_path, allow_duplicates=True)
            before = {path: path.read_text(encoding="utf-8") for path in written}

            with redirect_stdout(stdout):
                result = main(["hub-map", "--vault", str(vault_path), "--dry-run"])

            self.assertEqual(result, 0)
            self.assertFalse((vault_path / "MemoReef" / "Maps").exists())
            self.assertEqual({path: path.read_text(encoding="utf-8") for path in written}, before)
            output = stdout.getvalue()
            self.assertIn("Dry run hub map:", output)
            self.assertIn("AI Agents", output)
            self.assertIn("files that would change", output)

    def test_hub_map_is_idempotent_and_replaces_generated_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([
                Bookmark("Design systems one", "https://design.example/one", tags=["design-systems"], status="reef"),
                Bookmark("Design systems two", "https://design.example/two", tags=["design-systems"], status="reef"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(io.StringIO()):
                first = main(["hub-map", "--vault", str(vault_path)])
            after_first = {path: path.read_text(encoding="utf-8") for path in written}
            with redirect_stdout(io.StringIO()):
                second = main(["hub-map", "--vault", str(vault_path)])
            after_second = {path: path.read_text(encoding="utf-8") for path in written}

            self.assertEqual(first, 0)
            self.assertEqual(second, 0)
            self.assertEqual(after_second, after_first)
            for text in after_second.values():
                self.assertEqual(text.count("<!-- memoreef-connections:start -->"), 1)
                self.assertEqual(text.count("[[MemoReef/Maps/Hub - Design Systems|Design Systems]]"), 1)

    def test_hub_map_filters_noise_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Spatial art one", "https://example.com/one?utm_source=news", folders=["Bookmarks Bar", "2024"], tags=["art", "utm_source", "Lesezeichenleiste", "Action Triage", "Google"], status="reef"),
                Bookmark("Spatial art two", "https://example.com/two?utm_medium=email", folders=["Bookmarks Bar", "2024"], tags=["art", "12345", "Neuer Ordner", "Agent Brief", "Tool"], status="reef"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(io.StringIO()):
                result = main(["hub-map", "--vault", str(vault_path), "--min-drops", "2"])

            maps_dir = vault_path / "MemoReef" / "Maps"
            hub_names = {path.name for path in maps_dir.glob("Hub - *.md")}
            index = (maps_dir / "Emerging Hubs.md").read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("Hub - Art.md", hub_names)
            self.assertNotIn("Hub - Bookmarks Bar.md", hub_names)
            self.assertNotIn("Hub - 2024.md", hub_names)
            self.assertNotIn("Hub - Utm Source.md", hub_names)
            self.assertNotIn("Bookmarks Bar", index)
            self.assertNotIn("Utm Source", index)
            self.assertNotIn("Lesezeichenleiste", index)
            self.assertNotIn("Neuer Ordner", index)
            self.assertNotIn("Action Triage", index)
            self.assertNotIn("Agent Brief", index)
            self.assertNotIn("Google", index)
            self.assertNotIn("Tool", index)

    def test_app_dashboard_detects_latest_hub_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            write_bookmarks_to_vault([
                Bookmark("Search archive one", "https://example.com/one", tags=["local-search"], status="reef"),
                Bookmark("Search archive two", "https://example.com/two", tags=["local-search"], status="reef"),
            ], vault_path, allow_duplicates=True)

            with redirect_stdout(io.StringIO()):
                hub_result = main(["hub-map", "--vault", str(vault_path)])
            with redirect_stdout(io.StringIO()):
                app_result = main(["app", "--vault", str(vault_path)])

            html = (vault_path / "MemoReef" / "app" / "index.html").read_text(encoding="utf-8")
            self.assertEqual(hub_result, 0)
            self.assertEqual(app_result, 0)
            self.assertIn("Hub map", html)
            self.assertIn("MemoReef/Maps/Emerging Hubs.md", html)
            self.assertIn("hub-map", html)


if __name__ == "__main__":
    unittest.main()
