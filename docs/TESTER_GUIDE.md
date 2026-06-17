# MemoReef Tester Guide

MemoReef is an early local-first research memory tool. Please test it with a small real set of sources and tell us where the flow becomes confusing, slow, or brittle.

This is not a hosted app. It runs on your computer and writes Markdown files into a local vault folder you choose.

## What to test

Please try the full first-user path:

1. Install MemoReef from GitHub.
2. Import a small set of real bookmarks or links.
3. Start the local Review Mode app.
4. Add one real document through Import Dock.
5. Review a few Drops with Keep / Pearl / Sink.
6. Check the generated Markdown files.
7. Run one Pearl Dive query.
8. Open an issue or send feedback about anything unclear.

A good test takes 10–20 minutes. Use non-sensitive sources first.

## Requirements

You need:

- Python 3.11+
- Git
- A terminal
- A browser

Optional, only for scanned PDFs and image OCR:

- Tesseract OCR
- Poppler (`pdftoppm`)
- Tesseract language data if testing non-English OCR

On macOS, optional OCR tools can be installed with:

```bash
brew install tesseract poppler tesseract-lang
```

MemoReef still works without OCR tools for bookmarks, URL lists, CSV files, DOCX, TXT, Markdown, and text-based PDFs.

## 1. Install MemoReef

```bash
git clone https://github.com/SonicSeeds/memoreef.git
cd memoreef
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install -e .
```

If `python3.11` is not available, install Python 3.11+ first, then repeat the venv step.

```bash
python scripts/smoke_tester_readiness.py
```

It creates a temporary sample vault, imports example bookmarks, imports a URL list and a local Markdown document, exports a review session, regenerates the local app, checks key output files, then deletes the temporary vault. If this passes, the basic tester path is alive. A small green light. Not a religion.

## 2. Run the sample pilot first

This checks that the install works before you use your own data.

```bash
memoreef pilot --bookmarks examples/bookmarks.html --vault /tmp/memoreef-pilot --review-limit 3
open /tmp/memoreef-pilot/MemoReef/app/pilot.html
```

You should see a local pilot page and Markdown Drops under:

```text
/tmp/memoreef-pilot/MemoReef/Drops/
```

## 3. Import your own sources

Use a small export first. Do not start with your entire archive.

Browser bookmark export:

```bash
memoreef import /path/to/bookmarks.html --vault /tmp/memoreef-test-vault
```

Plain URL list, one URL per line:

```bash
memoreef import-links /path/to/links.txt --vault /tmp/memoreef-test-vault
```

CSV with `title,url,source,tags` columns:

```bash
memoreef import-csv /path/to/links.csv --vault /tmp/memoreef-test-vault
```

Local documents:

```bash
memoreef import-docs /path/to/research.pdf /path/to/brief.docx --vault /tmp/memoreef-test-vault
```

OCR for scanned PDFs or images:

```bash
memoreef import-docs --ocr --ocr-lang deu+eng /path/to/scanned.pdf --vault /tmp/memoreef-test-vault
```

## 4. Start Review Mode

```bash
memoreef serve --vault /tmp/memoreef-test-vault
open http://127.0.0.1:8765/
```

Review Mode should load Drift Drops from your local vault.

Controls:

- `←` Sink
- `↑` Pearl
- `→` Keep
- Open source: opens the original source link
- Tag kept/Pearls: adds local suggested tags to reviewed kept/Pearl Drops
- Continue later: stops without forcing more decisions

Decisions autosave directly into Markdown frontmatter while the local server is running.

## 5. Test Import Dock

In Review Mode, use **Import Dock** to add a document without returning to the terminal.

Try one of:

- PDF
- DOCX
- TXT
- Markdown
- PNG/JPG image
- scanned PDF with OCR enabled

Expected result:

- MemoReef imports the file.
- A new Markdown Drop appears in the vault.
- Review Mode refreshes with current Drift Drops.
- OCR only runs if enabled and local OCR tools are installed.

## 6. Check the Markdown output

Open:

```text
/tmp/memoreef-test-vault/MemoReef/Drops/
```

Each Drop should be a readable Markdown file with frontmatter. Document imports should include a `## Document text` section when text was extracted.

If you use Obsidian, open `/tmp/memoreef-test-vault` as a vault and inspect the `MemoReef` folder.

## 7. Run a Pearl Dive

Ask one question against your local sources:

```bash
memoreef dive "your question here" --vault /tmp/memoreef-test-vault --limit 5
memoreef app --vault /tmp/memoreef-test-vault
open /tmp/memoreef-test-vault/MemoReef/app/dive.html
```

Expected result:

- MemoReef writes a Dive Report under `MemoReef/answers/`.
- The report lists Retrieved Pearls with source URLs and Drop paths.
- If sources are weak or missing, the report names Uncharted Gaps instead of pretending.

## What feedback helps most

Please report:

- Did installation work from the README?
- Where did you get stuck?
- Did the terms Drops / Drift / Pearl / Reef make sense?
- Did Review Mode feel useful?
- Did Import Dock behave as expected?
- Did Pearl Dive retrieve useful Pearls or correctly name gaps?
- Did the Markdown output feel usable in Obsidian or another editor?
- What source type did you try: bookmarks, links, CSV, PDF, DOCX, image, scanned PDF?
- Would you use this again for a real project?

GitHub issues are ideal because they create visible project activity, but short direct feedback is also useful. For the exact feedback shape, see [Trusted Tester Feedback](TRUSTED_TESTER_FEEDBACK.md).

## Known limits

MemoReef is still early.

Current limits:

- No hosted account or cloud sync.
- No browser extension yet.
- No Obsidian plugin yet.
- No full article extraction yet.
- No LLM summaries yet.
- OCR extracts text from scanned/image files. Optional vision hooks can add visual/numeric artifacts, including calibrated vertical-bar digitized estimates, but broad chart/diagram understanding is still limited.
- Use a small test vault first before importing a large personal archive.

## Privacy note

MemoReef is local-first. It writes files on your computer and does not require an account, API key, hosted database, or cloud service.

Still, for first testing, use non-sensitive sources. Early software should earn trust one file at a time. Very dramatic. Also true.
