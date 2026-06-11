from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import unittest

from memoreef.bookmarks import parse_bookmarks_html, write_bookmarks_to_vault
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
