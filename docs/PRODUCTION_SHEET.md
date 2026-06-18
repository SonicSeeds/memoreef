# MemoReef Production Sheet for Codex

## Mission

Build MemoReef: a local-first bookmark-to-Obsidian app that turns browser bookmark exports and saved links into an agent-readable source library.

Core promise:

> Save sources. Let ideas surface.

Practical promise:

> Import browser bookmarks into an Obsidian vault, triage them quickly, enrich them with metadata, and let user-owned agents retrieve project-ready sources later.

## Product constraints

- Primary ingestion is **bulk bookmark import**, not Telegram-first link-by-link capture.
- Obsidian/Markdown is the durable storage target from day one.
- Local-first by default. Do not require a hosted backend for MVP.
- Agent-readable notes are a core output, not an afterthought.
- Metaphor should support usability, not obscure it.
- Avoid secrets in repo. Never commit API keys or user vault contents.

## Current repository state

Path: `/Users/sonic/MemoReef`

Implemented:

- Python package `memoreef` with CLI import, pilot, app, review, report, search, brief, and tagging workflows.
- Netscape bookmark HTML parser plus plain URL-list and CSV importers.
- Markdown writer for Obsidian-style Drops with Drift/Reef/Deep/Discarded/Treasure frontmatter.
- Import inspection, URL canonicalization, dedupe behavior, and import logs.
- Guided local pilot flow with generated `PILOT_README.md` and `app/pilot.html`.
- Filesystem-backed Review Mode server with direct Keep/Treasure/Sink autosave to the vault.
- Self-serve phone triage via trusted LAN/Tailscale URL/QR from `phone`.
- Local reviewed-Drop tagger via `tag-reviewed` and `POST /api/tag-reviewed`.
- Duplicate, link-check, metadata, garden-suggestion, library-search, and project-brief commands.
- Generated static local app pages: dashboard, pilot, tour, library, review, reports, briefs, and Drop detail pages.
- Premium static landing page and browser-only fallback prototypes.
- Unit tests covering the implemented workflows.

Run verification:

```bash
cd /Users/sonic/MemoReef
python3.11 -m unittest discover -s tests -v
python3.11 -m memoreef.cli tag-reviewed --help
rm -rf /tmp/memoreef-pilot
python3.11 -m memoreef.cli pilot --bookmarks examples/bookmarks.html --vault /tmp/memoreef-pilot --review-limit 3
python3.11 -m memoreef.cli tag-reviewed --vault /tmp/memoreef-pilot --dry-run
```

## MVP acceptance criteria

### Import

Given a browser bookmark HTML export, MemoReef should:

- parse all bookmarks;
- preserve folder hierarchy;
- create one Markdown file per bookmark;
- write into `<vault>/MemoReef/Drops/`;
- avoid filename collisions;
- include frontmatter fields:
  - title
  - url
  - type: drop
  - status: drift
  - agent_ready: true
  - treasure: false
  - folders
  - tags derived from folders, where safe.

### CLI

Current core commands:

```bash
memoreef import bookmarks.html --vault ~/Obsidian/Main
memoreef import-links links.txt --vault ~/Obsidian/Main
memoreef import-csv links.csv --vault ~/Obsidian/Main
memoreef pilot --bookmarks bookmarks.html --vault ~/Obsidian/Main
python3.11 -m memoreef.cli serve --vault ~/Obsidian/Main
python3.11 -m memoreef.cli phone --vault ~/Obsidian/Main
python3.11 -m memoreef.cli tag-reviewed --vault ~/Obsidian/Main --dry-run
```

Useful follow-on commands:

```bash
python3.11 -m memoreef.cli refresh-metadata --vault ~/Obsidian/Main --limit 50
python3.11 -m memoreef.cli extract-articles --vault ~/Obsidian/Main --limit 50
python3.11 -m memoreef.cli search-library --vault ~/Obsidian/Main --query "agent workflow"
python3.11 -m memoreef.cli brief --vault ~/Obsidian/Main --treasure-only
python3.11 -m memoreef.cli suggest-gardens --vault ~/Obsidian/Main
```

### Docs

README must explain:

- what MemoReef is;
- how to import bookmarks;
- what files it writes;
- current limitations;
- roadmap.

## Architecture recommendation

Keep the first public release as a small Python CLI. Reasons:

- zero Node dependency for first use;
- easy local execution;
- good fit for filesystem/Markdown operations;
- can later power a Tauri/local web UI.

Suggested folders:

```text
memoreef/
  __init__.py
  cli.py
  bookmarks.py
  vault.py          # split from bookmarks.py later
  enrich.py         # metadata/fetch/dead-link checks later
  triage.py         # Drift/Treasures/Deep/Projects state later
  agents.py         # agent briefing/export format later
examples/
docs/
tests/
```

## Next implementation tasks

### 1. Improve parser reliability

- Add tests for exported bookmark samples from Chrome, Brave/Arc, Firefox, Safari.
- Ensure nested folders are preserved correctly.
- Handle missing titles/URLs gracefully.
- Add `inspect` command that reports bookmark count and top folders without writing files.

### 2. Add dedupe

- Canonicalize URLs:
  - lowercase scheme/host;
  - strip common tracking params: `utm_*`, `fbclid`, `gclid`;
  - normalize trailing slash conservatively.
- If duplicate URL exists, do not create a second Drop unless `--allow-duplicates`.
- Store duplicate references in frontmatter or an import log.

### 3. Add import log

Write:

```text
<vault>/MemoReef/imports/YYYY-MM-DD-HHMMSS-import.md
```

Include:

- source file path;
- number parsed;
- number written;
- duplicates skipped;
- errors;
- command used.

### 4. Add enrichment stub

First pass now includes:

- HTTP HEAD/GET status check;
- current page title if fetch succeeds;
- source domain;
- readable web article extraction into `## Article text`;
- extraction status/error metadata for blocked, JS-only, non-HTML, or unreadable pages;
- dead-link flag.

Future optional:

- local summarizer;
- configured LLM provider;
- embeddings/index.

### 5. Add agent briefing format

For selected Drops or Projects, generate:

```text
<vault>/MemoReef/Agent Briefings/<topic>.md
```

Briefing structure:

- objective;
- sources with links;
- short source notes;
- open questions;
- suggested agent tasks.

### 6. UI later, not now

Do not build the swipe UI before the import/enrich/write pipeline is reliable.

When ready, evaluate:

- local FastAPI + web UI;
- Tauri desktop app;
- Obsidian plugin;
- browser extension.

## Naming / domain notes

Working name: **MemoReef**.

Known availability from first screen:

- `memoreef.com`: taken by a memorial/reef/burial-afterlife adjacent service.
- `memoreef.de`: available at time of check.
- GitHub `memoreef`: available at time of check.
- YouTube `@memoreef`: available at time of check.
- X/Instagram/TikTok: unclear or likely occupied; manually verify.

Recommended public structure:

- GitHub: `github.com/sonicseeds/memoreef`
- Landing: `memoreef.sonicseeds.de` or `memoreef.de`
- Domain: buy `memoreef.de` as low-cost defensive domain.

Avoid language that collides with the `.com` memorial service:

- memorial;
- afterlife;
- remains;
- eternal reef;
- remembrance reef.

## Tone and UX language

Use sparingly:

- Drop: saved link/bookmark.
- Drift: unsorted inbox.
- Reef: local source library.
- Deep: archive.
- Treasure: high-value source.
- Dive: search/agent retrieval.

Prefer human-readable labels in navigation:

- Inbox / Drift
- Library / Reef
- Pearls
- Projects
- Archive / Deep
- Ask / Dive

Do not overload v1 with Shoals, Coves, Tides, Expeditions unless the UI needs them.

## Security and privacy

- Do not upload user bookmarks to any service by default.
- Do not send URLs/content to LLM APIs unless user explicitly configures enrichment.
- Avoid storing credentials.
- Add `.gitignore` to prevent accidental committing of generated vaults, imports, `.env`, and test outputs.

## Definition of done for first public alpha

- CLI imports a real browser bookmark export without crashing.
- Generated Markdown opens cleanly in Obsidian.
- README has install/import instructions.
- Tests cover parser + writer + dedupe basics.
- Example output is committed, but no private user data is committed.
- Repo has MIT license or chosen license.
- Domain/landing page points to GitHub.
