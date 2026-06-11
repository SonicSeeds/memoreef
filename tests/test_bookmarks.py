from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest

from memoreef.bookmarks import Bookmark, canonicalize_url, parse_bookmarks_html, write_bookmarks_to_vault
from memoreef.cli import main


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


if __name__ == "__main__":
    unittest.main()
