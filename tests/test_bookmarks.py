from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from memoreef.bookmarks import Bookmark, bookmark_to_markdown, canonicalize_url, parse_bookmarks_html, write_bookmarks_to_vault
from memoreef.cli import main


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

    def test_apply_review_decisions_sink_updates_frontmatter(self):
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            vault_path = Path(tmp) / "vault"
            written = write_bookmarks_to_vault([Bookmark("Example Source", "https://example.com")], vault_path)
            decisions_path = Path(tmp) / "decisions.json"
            self.write_decisions(decisions_path, written[0], vault_path, "sink")

            with redirect_stdout(stdout):
                result = main(["apply-review-decisions", "--vault", str(vault_path), "--decisions", str(decisions_path)])

            content = written[0].read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertIn("status: discarded", content)
            self.assertIn("pearl: false", content)

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
            html = dashboard.read_text(encoding="utf-8")
            self.assertEqual(result, 0)
            self.assertTrue(dashboard.exists())
            self.assertIn("MemoReef local app", html)
            self.assertIn("Total Drops", html)
            self.assertIn("Drift", html)
            self.assertIn("Review Mode", html)
            self.assertIn("Agent proposals", html)
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


if __name__ == "__main__":
    unittest.main()
