# MemoReef FAQ

## Is MemoReef local-first?

Yes. MemoReef runs on your machine and writes Markdown files into a local vault. The current MVP does not require an account, hosted backend, database, API key, or cloud sync.

## Does MemoReef require Obsidian?

No. MemoReef writes plain Markdown, so the files can be opened anywhere. Obsidian is a natural fit because MemoReef creates an Obsidian-ready folder structure, frontmatter, and graph-friendly hub links.

## Is MemoReef an AI summarizer?

Not primarily. MemoReef is a source library for saved links, bookmarks, notes, and future agent workflows. AI features can sit on top later, but the core is local import, review, search, and source organization.

## What are Drops, Drift, Reef, and Pearls?

- **Drops** are saved links, highlighted passages, imported bookmarks, or local documents.
- **Drift** is the unsorted inbox for new Drops.
- **Reef** is the reviewed source library.
- **Pearls** are high-value sources worth citing, revisiting, or handing to agents.

## Can agents use my sources?

Yes. MemoReef stores sources as structured Markdown with metadata, tags, status, and hub links. That makes the library easier for local agents to search, cite, and build on.

## What works today?

MemoReef can import browser bookmark exports, URL lists, CSV files, PDFs, DOCX files, text files, Markdown files, and OCR-assisted image/scanned-PDF files; extract readable article text from saved HTTP/HTTPS pages; clip highlighted web text through a localhost bookmarklet; generate Markdown Drops; run a local Review Mode app with Import Dock drag-and-drop uploads; autosave Keep/Treasure/Sink decisions; create reports; generate hub maps; and build a static local app view.

## Can MemoReef extract article text from saved web pages?

Yes, for readable HTTP/HTTPS HTML pages. Run:

```bash
memoreef extract-articles --vault /tmp/memoreef-vault --limit 25
```

MemoReef writes extracted page content into `## Article text` and records extraction status/error metadata in frontmatter. Paywalls, blocked pages, JavaScript-only pages, non-HTML files, and pages without enough readable text are marked honestly.

## Can MemoReef import PDFs and DOCX files?

Yes. Use `import-docs` to turn local PDFs, DOCX files, text files, and Markdown files into source-memory Drops:

```bash
memoreef import-docs /path/to/research.pdf /path/to/brief.docx --vault /tmp/memoreef-vault
```

MemoReef writes the extracted text into a `## Document text` section and keeps source-file metadata in frontmatter. This is meant for NotebookLM-style source collection with Markdown/Obsidian output. Image files and scanned PDFs can be imported with `--ocr` when local OCR tools are installed.

## What about scanned PDFs, images, or graphics inside PDFs?

Text-based PDFs can be imported directly. Scanned/image PDFs can use `import-docs --ocr` when local OCR tools are installed (`tesseract`; scanned PDFs also need `pdftoppm`/Poppler). On macOS, install them with `brew install tesseract poppler tesseract-lang`. For German or mixed-language documents, pass `--ocr-lang deu+eng`. Graphics-heavy documents still need a later figure-aware vision layer before diagrams and charts can be described reliably.

## What is not implemented yet?

Figure-aware visual understanding for diagrams/charts, LLM summarization, deep semantic tagging, a browser extension, an Obsidian plugin, Notion/API connectors, and hosted multi-device sync are not part of the current MVP. Web article extraction is best-effort and may fail on paywalls, blocked pages, JavaScript-only pages, or pages without readable HTML.

## Is the mobile app real?

The current mobile app screenshot is a visual mockup. Phone triage is real through the local server on a trusted LAN or Tailscale network, but there is no standalone native mobile app yet.

## How do I import my bookmarks?

Export bookmarks from your browser as an HTML file, then run:

```bash
memoreef import /path/to/bookmarks.html --vault /tmp/memoreef-vault
```

For a guided local pilot:

```bash
memoreef pilot --bookmarks /path/to/bookmarks.html --vault /tmp/memoreef-pilot --review-limit 25
```

## Can I use Notion or other apps as sources?

Not directly through an API yet. The practical path today is export-first: export from Notion or another app to Markdown, CSV, text, or PDF, then import those files into MemoReef. Direct app connectors should come after the local Markdown import path is stable.

## Does MemoReef send my bookmarks to an external service?

No. The current MVP performs local file operations. It does not send your bookmarks to a hosted MemoReef service.
