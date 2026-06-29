# MemoReef

**Save sources. Let ideas surface.**

MemoReef turns saved links, documents, and notes into a local source memory for humans and AI agents. Review what matters, surface connections, and export bounded context without giving a cloud tool your whole archive.

It is not trying to be another bookmark manager. MemoReef is for people with messy saved research, half-forgotten sources, and projects that need grounded memory. The angle is simple: your context belongs to you; agents may learn from it only through explicit local, redacted, or shareable exports.

Want the Obsidian-specific walkthrough? See [Use MemoReef with Obsidian](https://memoreef.de/obsidian.html).

Testing MemoReef for the first time? Use the [Tester Guide](docs/TESTER_GUIDE.md). If you normally work through an AI coding agent, the tester guide includes a copy-paste agent install prompt. Building the full product? See the [Roadmap](docs/ROADMAP.md).

## Demo video

[![MemoReef concept overview](https://memoreef.de/img/og-memoreef-card.png)](https://memoreef.de/demo.html)

Watch the 69-second user-ready prototype demo. The video only loads on play.

It shows the local install path, real-source imports, Import Dock, Review Mode, and Markdown output.

## Install and run locally

MemoReef is a local Python app. It does not need a server, account, database, or API key.

Requirements:

- Python 3.11+
- Git

Optional OCR/visual-analysis requirements for scanned PDFs, image files, and PDF figure/table crops:

- Tesseract OCR
- Poppler (`pdftoppm`, `pdfinfo`) for scanned PDF page rendering and PDF page counts
- Tesseract language data for non-English OCR, for example German
- Pillow for optional visual-region crop detection (`python -m pip install -e ".[visual]"`)

On macOS, if `python3 --version` is older than 3.11, install a newer Python first:

```bash
brew install python@3.11
# or: uv python install 3.11
```

On macOS, install OCR tools only if you want `import-docs --ocr` for scanned PDFs or images:

```bash
brew install tesseract poppler tesseract-lang
```

Without these optional OCR tools, MemoReef still imports browser bookmarks, URL lists, CSV files, DOCX, TXT, Markdown, and text-based PDFs.

```bash
git clone https://github.com/SonicSeeds/memoreef.git
cd memoreef
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools
python -m pip install -e .
# optional, for PDF figure/table crop detection:
python -m pip install -e ".[visual]"
```

Create a local pilot vault from the included example bookmarks:

```bash
memoreef pilot --bookmarks examples/bookmarks.html --vault /tmp/memoreef-pilot --review-limit 3
open /tmp/memoreef-pilot/MemoReef/app/pilot.html
```

Or run commands directly from the checkout without installing the console script:

```bash
python3.11 -m memoreef.cli pilot --bookmarks examples/bookmarks.html --vault /tmp/memoreef-pilot --review-limit 3
```

Run Review Mode as a small local app when you want decisions autosaved directly back to the vault:

```bash
python3.11 -m memoreef.cli serve --vault /tmp/memoreef-pilot
open http://127.0.0.1:8765/
```

By default this binds only to `127.0.0.1`, loads up to 50 Drift Drops, and autosaves each Keep/Treasure/Sink decision directly to Markdown frontmatter in the vault. The Review Mode **Tag kept/Treasures** button then saves pending decisions and appends local agent-suggested tags to kept or Treasured Drops through the same filesystem bridge. No account, external network, hosted service, API key, database, or sync layer is required. Treat it as a local filesystem bridge: only run it for vaults you intend MemoReef to edit, and keep the default localhost bind unless you deliberately need otherwise.

The local app also includes **Import Dock**: a drag-and-drop/upload area for PDFs, DOCX, TXT, Markdown, and image files. It writes uploaded files directly into the selected vault as Markdown Drops. Enable OCR in Import Dock for scanned PDFs or images when local OCR tools are installed.

![MemoReef local Review Mode with Import Dock](docs/screenshots/import-dock-local-ui.png)

For phone triage on a trusted LAN or Tailscale network, start the same local app on the computer that has the vault:

```bash
python3.11 -m memoreef.cli phone --vault /tmp/memoreef-pilot
```

Each user runs this on their own computer, against their own vault. MemoReef prints phone-friendly URLs such as `http://192.168.x.x:8765/` or `http://100.x.x.x:8765/`, writes the primary URL to `MemoReef/phone-triage-url.txt`, and saves `MemoReef/phone-triage-qr.png` when the optional Python `qrcode` package is available. Open the URL or scan the QR from a phone on the same trusted LAN/Tailscale. Decisions write to that user's local vault through that user's computer.

The lower-level server command is still available:

```bash
python3.11 -m memoreef.cli serve --vault /tmp/memoreef-pilot --mobile
```

The command binds to `0.0.0.0` and warns that the vault write API is reachable from that network. Use it only on a trusted LAN or Tailscale network.

The pilot creates Markdown Drops under:

```text
/tmp/memoreef-pilot/MemoReef/Drops/
```

Import your own browser bookmarks, URL lists, CSV files with `title,url,source,tags` columns, or local documents:

```bash
memoreef import /path/to/bookmarks.html --vault /tmp/memoreef-vault
memoreef import-links /path/to/links.txt --vault /tmp/memoreef-vault
memoreef import-csv /path/to/links.csv --vault /tmp/memoreef-vault
memoreef import-tokwise ~/.tokwise/videos/videos.jsonl --vault /tmp/memoreef-vault
memoreef capture "signal: useful agent gateway idea https://example.com" --channel telegram --vault /tmp/memoreef-vault
memoreef extract-articles --vault /tmp/memoreef-vault --limit 25
memoreef import-docs /path/to/research.pdf /path/to/brief.docx --vault /tmp/memoreef-vault
memoreef import-docs --ocr /path/to/scanned.pdf /path/to/diagram.png --vault /tmp/memoreef-vault
memoreef import-docs --ocr --ocr-lang deu+eng /path/to/german-scan.pdf --vault /tmp/memoreef-vault
memoreef import-docs /path/to/complex-paper.pdf --vault /tmp/memoreef-vault --engine docling
```

`extract-articles` fetches saved HTTP/HTTPS URLs directly and writes the readable main page content into a `## Article text` section on each Drop. It records `article_extraction_status`, final/canonical URL, extraction time, and errors in frontmatter. Paywalls, blocked pages, JavaScript-only pages, non-HTML files, and pages without enough readable text are marked honestly instead of faked.

`import-tokwise` imports a local Tokwise `videos.jsonl` export — usually created by `tokwise auth from-browser && tw sync` — into short-form-video Drops. It preserves the TikTok URL, author/collection context, Tokwise classification, hashtags, stats, and transcript in local Markdown. MemoReef only reads the already-created JSONL file; it does not read browser cookies or contact TikTok itself.

`capture` turns Telegram/Discord/WhatsApp/iMessage-style messages into local Drops. It understands lightweight commands such as `/reef`, `/drop`, `reef:`, `drop:`, `signal:`, `youtube:`, and `x:` and stores the original message, source channel, sender label, and extracted URLs in Markdown. This gives dedicated-agent-machine setups a low-friction bridge from the channels where people already send links to the computer that owns the vault.

`import-docs` turns PDFs, DOCX files, text files, Markdown files, and image files into local Markdown Drops with source-file metadata and a `## Document text` section. It is useful for NotebookLM-style source collection when you want the durable output to stay in your own Markdown/Obsidian memory instead of a hosted notebook. Text-based PDFs work directly. Scanned/image PDFs and image files need `--ocr` plus local OCR tools (`tesseract`; scanned PDFs also need `pdftoppm`/Poppler). Use `--ocr-lang` for non-English documents, for example `deu+eng`.

By default, `import-docs` uses MemoReef's built-in local extractor. Optional extraction engines can be selected with `--engine`; the first supported optional engine is Docling (`python -m pip install -e ".[docling]"`, then `--engine docling`). MemoReef records the extraction engine in Drop frontmatter and falls back to the built-in local importer with an explicit warning when an optional engine is unavailable or fails. MinerU, Marker, and PyMuPDF4LLM are intentionally not base dependencies because their licenses or dependency posture are less clean for MemoReef's default local-first/MIT path.

For research papers, MemoReef also adds a `## Numeric artifacts` section when it can extract table-like numeric rows, when a vision backend returns validated structured numeric data, or when a vision backend returns calibrated vertical-bar chart geometry that MemoReef can digitize. This section is deliberately separate from visual prose: agents should answer exact-number questions only from quoted source table text or validated numeric artifacts. Machine-extracted CSV tables are candidates and include their source snippet, so agents must preserve context and avoid inventing missing headers. Digitized bar-chart values are calibrated estimates computed from y-axis tick calibration and bar-top pixel coordinates; if chart calibration is missing, inconsistent, or extrapolated, no value is promoted. If a chart is only summarized visually and no exact/digitized value is present in `## Numeric artifacts`, the correct answer is that the value was not extracted.

MemoReef also adds a `## Visual artifacts` section when it sees figure/table captions or table-like text in extracted PDF content. Optional page-image analysis is available through `--vision-command`, which renders the first PDF pages with Poppler, detects large visual regions such as charts/diagrams/tables, crops those regions, and passes each crop to your own local or cloud vision command. If no crop is detected on a page, MemoReef falls back to sending the full rendered page. This is off by default, so MemoReef stays local-first and does not require a vision model.

MemoReef warns when a PDF is large or when the file has more pages than the selected visual-analysis batch. By default it analyzes the first 10 pages; `--vision-page-limit` accepts 1–25.

Example optional vision hook:

```bash
memoreef import-docs paper.pdf --vault /tmp/memoreef-vault \
  --vision-command 'your-vision-cli --image {image} --prompt "{prompt}"' \
  --vision-page-limit 10
```

The command template supports `{image}`, `{page}`, and `{prompt}` placeholders.

## Product shape

MemoReef is a private source memory layer, not a generic bookmark manager:

- **Drops**: saved links or imported bookmarks.
- **Drift**: unsorted inbox state for new Drops.
- **Reef**: the living research memory in Markdown/Obsidian.
- **Deep**: long-term archive state for saved sources.
- **Treasures**: high-value Drops worth citing or using in emerging projects.
- **Shoals**: related source clusters.
- **Pearls**: distilled insights surfaced from Treasures and Shoals — the essence the octopus retrieves.
- **Pearl Dive**: agents search the reef for Treasures and return cited Pearls, source paths, and gaps.
- **AI export labels**: `ai_export: local_only`, `redacted`, or `shareable` tells MemoReef what can leave the vault when you create an agent context bundle.

## For agents

MemoReef is built for humans who read and agents who learn. Reviewed Drops, Treasures, Shoals, and Pearls can become grounded context for AI agents — from project handoffs to future Hermes `/learn` workflows that crystallize source material into reusable skills.

## Current MVP

Implemented:

- Parse Netscape-style browser bookmark HTML exports.
- Import plain text URL lists.
- Import CSV files with title, URL, source provenance, and tags.
- Import Tokwise short-form video archives (`videos.jsonl`) as local transcript/classification Drops.
- Capture URLs from Telegram/Discord/iMessage-style messages into local source Drops.
- Extract readable article text from saved HTTP/HTTPS web pages into `## Article text` sections with honest status/error metadata.
- Import local PDF, DOCX, text, Markdown, and OCR-assisted image/scanned-PDF files into source-memory Drops.
- Extract PDF numeric table rows into Numeric artifacts for exact-number answers.
- Digitize calibrated vertical bar chart geometry from vision output into CSV numeric artifacts.
- Extract PDF figure/table captions, table-like text, optional visual-region crops, and optional vision-command descriptions into Visual artifacts sections.
- Preserve folder path as Markdown frontmatter.
- Write one Markdown file per bookmark.
- Store files in an Obsidian-ready folder structure.
- Mark imported items as `status: drift`, `agent_ready: true`, `ai_export: local_only`, and triage-ready Drop frontmatter.
- Export and apply local Review Mode decisions.
- Serve local Review Mode with direct vault autosave for decisions.
- Generate agent finish plans, deterministic proposal drafts, and local agent tags for kept or Treasured Drops.
- Export privacy-labeled agent context bundles with a source contract, manifest, and redacted/shareable source files.
- Generate Obsidian hub map notes and Drop-to-hub `[[links]]` so reviewed Drops form visible graph clusters.
- Create duplicate, dead-link, metadata, garden suggestion, and library search reports.
- Generate a refined static local app with dashboard, pilot, tour, library, Pearl Dive, review, reports, briefs, and Drop detail pages.
- Provide a browser-only Review Mode prototype with sample data until a real review-session JSON is loaded, a non-functional mobile app mockup, and the live cinematic landing page at [memoreef.de](https://memoreef.de/).

Not implemented yet:

- LLM-generated summaries and deep semantic tagging.
- Browser extension.
- Obsidian plugin.
- Hosted sync or multi-device account layer.

## Built with Codex-assisted development

MemoReef is being built with focused Codex tasks that keep changes small, reviewable, and test-backed. Codex contributes implementation work such as importers, tests, UI prototypes, refactors, and documentation, while Tao/Hermes handles product direction, architecture, taste, verification, and repo orchestration.

See [docs/GRANT_BRIEF.md](docs/GRANT_BRIEF.md) for the grant-oriented project narrative.

For common questions about local-first storage, Obsidian support, agent use, and roadmap scope, see [docs/FAQ.md](docs/FAQ.md).

## Screenshots

![MemoReef full landing page from surface to octopus reef](docs/screenshots/landing-page-octopus-pearls.png)

![MemoReef Reef Current fish and shoal visualization](docs/screenshots/reef-current-fish-shoals.png)

| Review Mode local app: autosaves to vault | Product tour: octopus hero |
| --- | --- |
| ![MemoReef Review Mode local app with vault autosave](docs/screenshots/review-mode-swipe.png) | ![MemoReef product tour with octopus hero](docs/screenshots/tour-octopus-eye-bottom-aligned.png) |

## Example output

```markdown
---
title: "Local AI Agents for Small Teams"
url: "https://example.com/local-agents"
type: drop
status: drift
agent_ready: true
ai_export: local_only
treasure: false
folders:
  - "AI Agents"
tags:
  - ai-agents
---

# Local AI Agents for Small Teams

Source: [https://example.com/local-agents](https://example.com/local-agents)

## Summary

_Not enriched yet._

## Notes

## Agent Brief

- Status: Drift
- Suggested next action: triage this Drop.
```

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Run the sample import:

```bash
rm -rf /tmp/memoreef-vault
python3.11 -m memoreef.cli import examples/bookmarks.html --vault /tmp/memoreef-vault
find /tmp/memoreef-vault/MemoReef/Drops -type f
```

Run URL list or CSV imports:

```bash
python3.11 -m memoreef.cli import-links links.txt --vault /tmp/memoreef-vault
python3.11 -m memoreef.cli import-csv links.csv --vault /tmp/memoreef-vault
```

## Pilot: try MemoReef with your bookmarks

Export your bookmarks from your browser as an HTML file. In most browsers this is under Bookmark Manager or Library, then Export Bookmarks.

Run the guided local pilot:

```bash
rm -rf /tmp/memoreef-pilot
python3.11 -m memoreef.cli pilot --bookmarks /path/to/bookmarks.html --vault /tmp/memoreef-pilot --review-limit 25
open /tmp/memoreef-pilot/MemoReef/app/pilot.html
open /tmp/memoreef-pilot/MemoReef/app/gravity.html
open /tmp/memoreef-pilot/MemoReef/app/tour.html
```

Plain URL lists and CSV exports work too:

```bash
python3.11 -m memoreef.cli pilot --links /path/to/links.txt --vault /tmp/memoreef-pilot
python3.11 -m memoreef.cli pilot --csv /path/to/links.csv --vault /tmp/memoreef-pilot
```

The pilot command imports your export, creates a review session, creates a duplicate report, generates static app pages, and writes `MemoReef/PILOT_README.md`. It is offline-only: no network calls, no AI calls, no backend, and no server.

The generated pilot app pages are self-contained HTML with inline CSS. They are designed as a calm local workspace. `gravity.html` adds a visual reef layer: Shoals become colored clusters, Drops become fish, and Treasures glow with more mass. The public cinematic landing page lives at [memoreef.de](https://memoreef.de/).

Review a few items with the local app bridge:

```bash
python3.11 -m memoreef.cli serve --vault /tmp/memoreef-pilot --limit 25
open http://127.0.0.1:8765/
```

The local app opens Review Mode, loads Drift Drops from the vault, and autosaves decisions directly back to the Markdown files as you sort.

## Clip highlighted text into your local research memory

Start the local MemoReef server against the vault you want to write to:

```bash
memoreef serve --vault /path/to/vault
```

Then create a browser bookmark named `Clip to Reef` and paste this bookmarklet as the bookmark URL:

```text
javascript:(function(){const d={url:window.location.href,title:document.title,selection:String(window.getSelection())};fetch('http://127.0.0.1:8765/api/drop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(j=>alert(j.clipped?'💧 Highlight clipped to Reef!':'💧 Page dropped to Reef!')).catch(()=>alert('❌ MemoReef local server is not running on http://127.0.0.1:8765.'));})();
```

Highlight useful text on any webpage, click `Clip to Reef`, and MemoReef saves the page title, source URL, and selected passage as a new local Markdown Drop in the connected vault. Highlight clips are marked with `has_clipped_selection: true`, `clip_type: "highlight"`, and a readable `## Clipped selection` block so humans and agents can return to the trusted source context later.

If nothing is highlighted, the same bookmarklet still saves the current page title and URL as a normal Drop.

This is a localhost-only bridge to your own running `memoreef serve` process, not a browser extension, hosted sync service, database, or cloud capture tool.

## Capture from Telegram, Discord, WhatsApp, or iMessage gateways

Dedicated-agent-machine setups often split capture and memory across devices: the human is on a MacBook or phone, while the agent and Obsidian vault live on a Mac mini, server, or VPS. MemoReef's channel capture path is the bridge.

For direct CLI capture:

```bash
memoreef capture "/reef https://example.com/useful-source" --channel whatsapp --vault /path/to/vault
memoreef capture "reef: https://example.com/useful-source" --channel telegram --vault /path/to/vault
memoreef capture "signal: agent gateway pattern https://example.com/thread" --channel discord --sender nika --vault /path/to/vault
```

For bot or gateway adapters, keep `memoreef serve` running on the computer with the vault and POST incoming messages to `/api/capture`:

```bash
curl -X POST http://127.0.0.1:8765/api/capture \
  -H 'Content-Type: application/json' \
  -d '{"channel":"telegram","sender":"nika","text":"signal: https://example.com/thread"}'
```

The endpoint accepts `text` or `message`, extracts every `http(s)` URL, and writes one Drop per URL. Supported command prefixes are `/reef`, `/drop`, `reef:`, `drop:`, `signal:`, `youtube:`, and `x:`. Real Telegram/Discord/WhatsApp/iMessage bots should stay as thin adapters: receive message, pass `{channel, sender, text}` to the local MemoReef server, and let MemoReef write the vault.

Phone/LAN/Tailscale mode uses the same real Review Mode and the same local Markdown writes. Each user runs this on their own computer against their own vault:

```bash
python3.11 -m memoreef.cli phone --vault /tmp/memoreef-pilot --limit 25
```

The command prints the phone URLs, saves `MemoReef/phone-triage-url.txt`, optionally saves a QR PNG when the optional `qrcode` package is available, and keeps the local Review Mode server running. The phone talks to that user's computer; that computer writes Keep/Treasure/Sink decisions to that user's local vault.

The lower-level server command is also available:

```bash
python3.11 -m memoreef.cli serve --vault /tmp/memoreef-pilot --limit 25 --lan
```

Keep the server running on the computer with the vault, put the phone on the same trusted LAN or Tailscale network, then open one of the printed `http://<computer-ip>:8765/` URLs on the phone. This is not a hosted sync layer or mobile app.

The browser-only fallback still works. It opens with clearly marked sample data. To review your real bookmarks without running the local server, load one of the JSON files generated by the pilot command:

```bash
open /tmp/memoreef-pilot/MemoReef/review-sessions/
```

In Review Mode, click **Load review session JSON** and select a `*-review-session.json` file from that folder. Do not paste the folder path into Terminal by itself; folder paths are locations, not commands.

After reviewing, export decisions from the browser, then apply them:

```bash
python3.11 -m memoreef.cli apply-review-decisions --vault /tmp/memoreef-pilot --decisions /path/to/memoreef-review-decisions.json --dry-run
python3.11 -m memoreef.cli apply-review-decisions --vault /tmp/memoreef-pilot --decisions /path/to/memoreef-review-decisions.json
python3.11 -m memoreef.cli app --vault /tmp/memoreef-pilot
```

After review, create graph-visible hub notes and reopen the app:

```bash
python3.11 -m memoreef.cli hub-map --vault /tmp/memoreef-pilot --dry-run
python3.11 -m memoreef.cli hub-map --vault /tmp/memoreef-pilot
python3.11 -m memoreef.cli app --vault /tmp/memoreef-pilot
open /tmp/memoreef-pilot/MemoReef/Maps/Emerging\ Hubs.md
```

`hub-map` is local-only. It reads reviewed useful Drops, creates `MemoReef/Maps/Emerging Hubs.md` plus per-hub notes, and writes a generated `MemoReef Connections` section with Obsidian `[[links]]` into linked Drops. Re-running it updates the generated sections instead of duplicating links.

After review, create a small project brief and reopen the app:

```bash
python3.11 -m memoreef.cli brief --vault /tmp/memoreef-pilot --limit 10
python3.11 -m memoreef.cli app --vault /tmp/memoreef-pilot
open /tmp/memoreef-pilot/MemoReef/app/briefs.html
```

Send back feedback from the checklist in `app/pilot.html`: whether import worked, which steps were confusing, whether useful sources surfaced, what was missing, and whether you would use it again.

Open the browser-only Review Mode fallback:

```bash
open site/swipe.html
```

Export a local review session JSON from a vault, then open the browser-only Review Mode and load the JSON with the file picker:

```bash
python3.11 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault
open site/swipe.html
```

The separate mobile app mockup at `site/mobile.html` is visual only. Real phone triage uses the filesystem-backed server above: run `phone` on the computer with the vault and open the printed LAN/Tailscale URL or generated QR on the phone.

Create filtered review sessions for focused queues:

```bash
python3.11 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --project "AI Agents"
python3.11 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --shoal "Automation"
python3.11 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --treasure-only
python3.11 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --status drift --exclude-status discarded
python3.11 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --status drift --limit 25
```

Filtered review sessions are local-only and do not modify files. Different filter groups combine together, while repeated values inside one group broaden that group.

Search your local library:

```bash
python3.11 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "agent workflow"
python3.11 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "workflow" --project "AI Agents"
python3.11 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "research" --treasure-only
python3.11 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "automation" --status drift --exclude-status discarded
```

Library search is local-only and read-only. It searches Markdown Drops and writes JSON results under `MemoReef/search` unless `--output` is provided.

Run a Pearl Dive to retrieve cited Pearls for a question:

```bash
python3.11 -m memoreef.cli dive "agent workflow" --vault /tmp/memoreef-vault
python3.11 -m memoreef.cli dive "research" --vault /tmp/memoreef-vault --treasure-only --limit 5
```

Pearl Dive is local-only and read-only against Drops. It writes a Markdown Dive Report under `MemoReef/answers/*-dive-report.md` unless `--output` is provided, includes retrieved Pearls with source URLs and Drop paths, and names Uncharted Gaps when the local reef cannot support an answer.

Export selected Drops into a Markdown project brief:

```bash
python3.11 -m memoreef.cli brief --vault /tmp/memoreef-vault --project "AI Agents"
python3.11 -m memoreef.cli brief --vault /tmp/memoreef-vault --project "AI Agents" --treasure-only --limit 10
```

Project briefs are local-only and read-only against Drops. They write Markdown under `MemoReef/briefs/*-project-brief.md` unless `--output` is provided, include source URLs and Drop metadata, and add an Agent handoff section that tells an agent to use only listed sources, cite URLs, note gaps, and avoid invented claims.

Export a bounded agent context bundle:

```bash
# Default: only Drops labeled ai_export: redacted or shareable are copied into the bundle.
python3.11 -m memoreef.cli export-agent-context --vault /tmp/memoreef-vault --project "AI Agents"

# Deliberate override when you personally want local-only Drops included too.
python3.11 -m memoreef.cli export-agent-context --vault /tmp/memoreef-vault --project "AI Agents" --include-local-only
```

Every new Drop starts with `ai_export: local_only`. Change individual Drops to `ai_export: redacted` or `ai_export: shareable` before exporting context to another agent. The command writes `MemoReef/agent-context/<timestamp>/README.md`, `manifest.json`, and source Markdown files. The README contains the source contract; the manifest records exported vs excluded sources; redacted files keep titles, URLs, labels, summaries, and short evidence snippets without copying the full article/document/highlight text. This is the current private-AI-context lane: export the minimum useful context, not the whole reef.

Create a complete local demo vault:

```bash
python3.11 -m memoreef.cli demo --output /tmp/memoreef-demo
open /tmp/memoreef-demo/MemoReef/app/pilot.html
open /tmp/memoreef-demo/MemoReef/app/gravity.html
open /tmp/memoreef-demo/MemoReef/app/tour.html
open /tmp/memoreef-demo/MemoReef/app/index.html
```

The demo command writes fictional sample Drops and generates local review, duplicate, garden, search, Pearl Dive, project brief, agent-plan, pilot checklist, visual Gravity Map, product tour, Drop detail, review launcher, reports, briefs, and static app artifacts. Open `MemoReef/app/pilot.html` first for the guided checklist, then use the Gravity Map, tour, dashboard, library, Pearl Dive, review, reports, briefs, and example Drop detail pages. It does not use a backend, network call, AI call, or secrets.

Review Mode can export `memoreef-review-decisions.json` from the browser. The CLI can apply those decisions back to Markdown frontmatter.

Apply exported Review Mode decisions back to Markdown Drop frontmatter:

```bash
python3.11 -m memoreef.cli apply-review-decisions --vault /tmp/memoreef-vault --decisions /tmp/memoreef-review-decisions.json --dry-run
python3.11 -m memoreef.cli apply-review-decisions --vault /tmp/memoreef-vault --decisions /tmp/memoreef-review-decisions.json
```

This updates `status`, `treasure`, and `triaged_at` only. It does not move or delete files.

Tag kept and Treasured Drops with local agent-suggested tags:

```bash
python3.11 -m memoreef.cli tag-reviewed --vault /tmp/memoreef-vault --dry-run
python3.11 -m memoreef.cli tag-reviewed --vault /tmp/memoreef-vault
```

`tag-reviewed` scans Drops that are already kept (`status: reef` or `status: deep`) or marked `treasure: true`, then appends conservative lowercase/hyphen tags from the Drop title, URL, folder path, projects, shoals, page metadata, and note text. It preserves existing tags, skips Drift/Sink items, writes `agent_tagged_at` and `agent_tag_count`, and does not call an external API. In local server Review Mode, the **Tag kept/Treasures** button first saves pending decisions and then calls this same local tagger.

Create an agent finish plan for the remaining unreviewed Drops:

```bash
python3.11 -m memoreef.cli plan-agent-finish --vault /tmp/memoreef-vault --decisions /tmp/memoreef-review-decisions.json
```

The agent finish plan JSON groups reviewed taste examples into Treasure, Keep, and Sink, then lists the remaining Drops for a later agent task. It does not modify Markdown, and it does not classify the remaining Drops yet.

Draft agent proposals from an agent finish plan:

```bash
python3.11 -m memoreef.cli draft-agent-proposals --plan /tmp/agent-finish-plan.json
```

The agent proposals JSON suggests status, Treasure state, confidence, priority, note location, and rationale for each remaining Drop using deterministic local heuristics.

Apply accepted agent proposals back to Markdown Drop frontmatter:

```bash
python3.11 -m memoreef.cli apply-agent-proposals --vault /tmp/memoreef-vault --proposals /tmp/agent-proposals.json --dry-run
python3.11 -m memoreef.cli apply-agent-proposals --vault /tmp/memoreef-vault --proposals /tmp/agent-proposals.json
```

Proposals marked `requires_user_review: true` are skipped by default. Pass `--include-needs-review` to apply them deliberately. This updates frontmatter only and does not move, delete, or retag files.

Create a local duplicate report:

```bash
python3.11 -m memoreef.cli duplicate-report --vault /tmp/memoreef-vault
```

The duplicate report groups exact canonical URLs, same-domain clusters, and conservative similar-title matches. It is local-only, does not call the network, and does not modify, move, or delete files.

Check saved links directly:

```bash
python3.11 -m memoreef.cli check-links --vault /tmp/memoreef-vault --limit 100 --timeout 5
```

The link check report classifies saved URLs as ok, broken, suspicious, or unknown using direct HTTP HEAD/GET requests to the saved URLs only. It does not use third-party APIs and does not modify, move, or delete files.

Refresh basic page metadata:

```bash
python3.11 -m memoreef.cli refresh-metadata --vault /tmp/memoreef-vault --dry-run
python3.11 -m memoreef.cli refresh-metadata --vault /tmp/memoreef-vault --limit 50 --timeout 5
python3.11 -m memoreef.cli extract-articles --vault /tmp/memoreef-vault --dry-run
python3.11 -m memoreef.cli extract-articles --vault /tmp/memoreef-vault --limit 50 --timeout 8
```

Metadata refresh fetches saved URLs directly, extracts page title, description, canonical URL, and hostname, then updates only the related frontmatter fields. Article extraction fetches saved HTTP/HTTPS URLs directly and writes the readable main page text to `## Article text`. Both commands avoid third-party APIs; extraction failures such as paywalls, JavaScript-only pages, unsupported content types, and network errors are recorded in Drop frontmatter instead of hidden.

Suggest projects and shoals from existing curated Drops:

```bash
python3.11 -m memoreef.cli suggest-gardens --vault /tmp/memoreef-vault
```

Garden suggestions are local-only heuristic reports. They compare unsorted Drops to Drops that already have projects or shoals, suggest only labels you already use, and do not modify, move, or delete files.

Apply accepted garden suggestions:

```bash
python3.11 -m memoreef.cli apply-garden-suggestions --vault /tmp/memoreef-vault --suggestions /tmp/garden-suggestions.json --dry-run --accept-all
python3.11 -m memoreef.cli apply-garden-suggestions --vault /tmp/memoreef-vault --suggestions /tmp/garden-suggestions.json --accept-project "AI Agents" --accept-shoal "Automation"
```

Applying garden suggestions only writes accepted project and shoal labels from a local suggestion report. It preserves existing labels, does not duplicate labels, and does not modify any other frontmatter fields or Markdown body.

Generate the static local app dashboard:

```bash
python3.11 -m memoreef.cli app --vault /tmp/memoreef-vault
open /tmp/memoreef-vault/MemoReef/app/tour.html
open /tmp/memoreef-vault/MemoReef/app/gravity.html
open /tmp/memoreef-vault/MemoReef/app/pilot.html
open /tmp/memoreef-vault/MemoReef/app/index.html
open /tmp/memoreef-vault/MemoReef/app/library.html
open /tmp/memoreef-vault/MemoReef/app/review.html
open /tmp/memoreef-vault/MemoReef/app/reports.html
open /tmp/memoreef-vault/MemoReef/app/briefs.html
```

The app command writes `index.html`, `gravity.html`, `pilot.html`, `tour.html`, `library.html`, `review.html`, `reports.html`, `briefs.html`, and one generated Drop detail page under `app/drops/` for each local Drop. The Gravity Map turns Shoals into colored clusters and Drops into fish, with mass based on Treasure marks, review status, metadata, labels, and recency. The pilot page gives early users a guided local checklist; the tour page is generated from local vault data and explains the product story: messy saves, Treasures, retrieved Pearls, clutter reports, agent handoff artifacts, project briefs, library search, Drop detail pages, and why local Markdown matters. The dashboard summarizes Drop counts, shows the latest local review/agent/search/brief artifacts, links to the expanded app pages, and points to the next recommended workflow step. It is static HTML and does not start a backend.

The static site prototypes use inline sample data. The generated local app pages are created from real vault files and local JSON artifacts. None of them start a backend.

## Near-term roadmap

1. Dogfood the current local server with Nika’s own real sources: import, Review Mode, Import Dock, Pearl Dive, and one agent-context bundle.
2. Make first-run setup calmer: one guided command, clearer empty states, and easier bookmarklet setup.
3. Improve privacy controls around context export: batch relabeling, bundle preview, and clearer redaction boundaries.
4. Add richer source anchors and quote extraction for articles/documents so agents can distinguish quotes, summaries, estimates, and missing evidence.
5. Surface duplicate/dead-link/garden suggestions directly inside the app, not only as JSON reports.
6. Keep website/demo copy aligned with the shipped local app before broader tester outreach.

## License

MIT, unless changed before public release.
