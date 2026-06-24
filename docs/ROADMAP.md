# MemoReef Roadmap — the building

MemoReef’s goal is trustworthy research-source memory: a local-first system where humans and AI agents can build from saved sources without losing source truth.

This is the product map, not a wishlist. A room is done only when a real user can exercise it and the repo has a verification path.

## North star

Turn saved links, notes, documents, and web sources into a private Markdown source library that supports review, retrieval, citation, and agent handoff.

## Room 1 — First real user readiness

Purpose: a technical/curious tester can clone MemoReef, run it, import their own small source set, and tell us where it breaks.

Status: tester-ready; awaiting 2–3 trusted tester signals.

Acceptance criteria:

- README has a clean clone/install/run path.
- `docs/TESTER_GUIDE.md` walks through sample data, real imports, Review Mode, Import Dock, Pearl Dive, and feedback.
- A smoke script verifies the tester path from a clean checkout.
- A tester can import at least one browser bookmark export, URL list, and local document.
- Review Mode can autosave Keep/Treasure/Sink decisions to Markdown frontmatter.
- Bookmarklet clipping works against the localhost bridge.
- At least 2–3 trusted testers try it and leave issues, stars, or concrete feedback.

## Room 2 — Ingestion reef

Purpose: sources enter MemoReef reliably without becoming mystery sludge.

Current capabilities:

- Browser bookmark HTML import.
- URL list import.
- CSV import.
- Document import for PDF, DOCX, TXT, Markdown, and images.
- OCR-assisted scanned/image import when local OCR tools are installed.
- Local Import Dock in Review Mode.
- Bookmarklet clipping for current page and highlighted text.

Next acceptance criteria:

- Add a guided `first-run` command or equivalent checklist surface.
- Add browser-extension or packaged bookmarklet setup that is easier than copying JavaScript manually.
- Add safer large-archive guidance: start small, then scale.
- Add richer import diagnostics for unsupported files and missing OCR tools.

## Room 3 — Evidence extraction

Purpose: preserve what matters from sources while marking uncertainty honestly.

Current capabilities:

- Best-effort web article extraction into `## Article text` with status/error metadata.
- Document text extraction.
- Optional `--engine docling` adapter for complex local document extraction, with built-in fallback.
- Visual artifacts from captions/table-like text.
- Optional bounded `--vision-command` for PDF page/crop analysis.
- Numeric artifacts from extracted table candidates.
- Validated vision numeric artifacts.
- Calibrated vertical-bar chart digitization as `digitized_estimate` values.

Next acceptance criteria:

- Easier first-run controls for article extraction from imported URL/bookmark Drops.
- Source quote extraction with stable anchors where possible.
- Benchmark Docling on simple, scanned, and table/formula-heavy PDFs before making it part of `--engine auto`.
- Chart digitization beyond simple vertical bars only after calibration rules are safe.
- Per-artifact confidence/limits visible in generated Drop pages.

## Room 4 — Review and curation

Purpose: users quickly separate signal from sediment before agents act.

Current capabilities:

- Drift/Reef/Deep/Discarded states.
- Treasure marking.
- Review Mode with keyboard controls and autosave.
- Local tag suggestions for kept or Treasured Drops.
- Discarded archive path with delete marker.

Next acceptance criteria:

- Clearer first-run empty states.
- Session resume that is obvious to non-technical testers.
- Better duplicate/dead-link triage surfaced inside the app.
- Optional Obsidian graph/hub pass after review.

## Room 5 — Retrieval and Pearl Dive

Purpose: MemoReef becomes useful after ingestion, not just tidy.

Current capabilities:

- Local library page/search over generated app pages.
- Brief generation from filtered Drops.
- Pearl Dive CLI that retrieves cited local-source nuggets and writes Dive Reports.
- Pearl Dive app surface in the generated local app.
- Reports for duplicates, links, metadata, gardens/projects/shoals.

Next acceptance criteria:

- Agent-assisted answer synthesis from Dive Reports only, with source files/URLs cited.
- No answer from unsourced memory unless explicitly labeled.
- Clear distinction between quote, summary, estimate, and missing evidence.

## Room 6 — Agent handoff

Purpose: agents can work from grounded user-owned context without inventing the archive.

Current capabilities:

- Agent finish plans.
- Deterministic proposal drafts.
- Apply accepted proposals with safety checks.
- Agent-ready Markdown Drops and reports.

Next acceptance criteria:

- Export bundle for external agents: task, relevant Drops, citations, gaps.
- Import agent outputs as proposals, not silent mutations.
- Source-contract text embedded in handoff bundles.
- Regression tests for unsafe proposal paths and stale source references.

## Room 7 — Public open-source and grant readiness

Purpose: MemoReef is credible to testers, funders, and contributors.

Current capabilities:

- Public GitHub repo.
- MIT license.
- README, grant brief, production sheet, tester guide, feedback guide, and trusted tester invite copy.
- Demo page and screenshots.
- GitHub issue templates for tester feedback, bugs, and feature requests.
- Unit test suite and fresh-clone smoke path verified from GitHub `main`.

Next acceptance criteria:

- Keep fresh-clone tester smoke green as the install path changes.
- Keep GitHub issue templates aligned with the tester flow.
- Keep public roadmap current and honest.
- Keep demo video aligned with actual shipped flow.
- 2–3 trusted tester signals exist before broad launch.

## Operating rule

Build vertically. Each pass should leave MemoReef more usable by a real person, not just more impressive to describe.

Pretty architecture without exits is a maze. MemoReef is not allowed to become a maze.
