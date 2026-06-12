# MemoReef Codex Task Queue

MemoReef is being built as a Codex-assisted open-source project. Tao owns product direction and verification; Codex should implement focused, test-backed changes in small branches.

## Working model

- Repo: `https://github.com/SonicSeeds/memoreef`
- Default branch: `main`
- Development machine for Codex: Nika's MacBook
- Orchestration/verification: Tao on Mac Mini or repo CI once added
- Rule: one Codex task = one branch = one small PR or push after review

## Task 1 — Import inspect command

### Goal
Add a read-only CLI command that inspects a browser bookmark export without writing files.

### Command

```bash
python3 -m memoreef.cli inspect examples/bookmarks.html
```

### Acceptance criteria

- Prints total bookmark count.
- Prints top-level folder names and counts.
- Does not create or modify vault files.
- Has unit tests.
- Existing tests still pass:

```bash
python3 -m unittest discover -s tests
```

## Task 2 — URL canonicalization and dedupe

### Goal
Prevent duplicate Drops for the same URL during import.

### Requirements

- Add URL canonicalization utility.
- Strip common tracking params: `utm_*`, `fbclid`, `gclid`.
- Lowercase scheme and host.
- Preserve path case and meaningful query params.
- During import, skip duplicate canonical URLs by default.
- Add optional `--allow-duplicates` flag.
- Add tests for duplicate imports.

### Acceptance criteria

- Duplicate URLs produce one Drop by default.
- `--allow-duplicates` writes separate files.
- Tests cover canonicalization and import behavior.

## Task 3 — Import log

### Goal
Write an import report into the vault after each import.

### Output path

```text
<vault>/MemoReef/imports/YYYY-MM-DD-HHMMSS-import.md
```

### Include

- source file path
- command options
- parsed bookmark count
- written Drop count
- skipped duplicate count
- errors/warnings

### Acceptance criteria

- Import log is created for every import.
- Tests verify log creation and key fields.

## Task 3A — Dedupe policy note for social/X imports

Browser bookmark imports can dedupe by canonical target URL, but social imports must not blindly discard different posts that point to the same target URL.

Future X/social import behavior:

- preserve each saved post by `source_url` or platform post ID;
- store the outbound article/page as `target_url` plus `canonical_target_url`;
- group multiple posts pointing to the same target into a Shoal or mentions list;
- dedupe social imports by source post identity, not by outbound target URL alone.

This is a design constraint for future importer tasks, not an implementation requirement for Task 3.

## Task 4 — CSV / URL list importer

### Goal
Support simple imports beyond browser HTML.

### Commands

```bash
python3 -m memoreef.cli import-links links.txt --vault /tmp/memoreef-vault
python3 -m memoreef.cli import-csv links.csv --vault /tmp/memoreef-vault
```

### Expected formats

`links.txt`:

```text
https://example.com/a
https://example.com/b
```

`links.csv` columns:

```text
title,url,source,tags
```

### Acceptance criteria

- URL list imports use URL as fallback title.
- CSV imports preserve title and tags.
- Tests included.

## Task 5 — Drift triage data model

### Goal
Prepare for the swipe/keyboard UI by formalizing statuses.

### Statuses

- `drift`
- `reef`
- `deep`
- `discarded`

### Additional fields

- `pearl: true|false`
- `projects: []`
- `shoals: []`
- `triaged_at`

### Acceptance criteria

- Markdown writer supports these fields.
- Existing Drops remain valid.
- Tests cover default and explicit states.

## Task 6 — Static Drift triage prototype

### Goal
Create a local web prototype for the Tinder-like triage flow using sample JSON data. This is not yet connected to the filesystem.

### Path

```text
site/triage.html
```

### Requirements

- Marine MemoReef visual language.
- Card stack for Drops.
- Keyboard shortcuts:
  - `K`: keep in Reef
  - `P`: mark Pearl
  - `D`: send to Deep
  - `X`: discard
  - `ArrowRight`: next
- Visible decision history.
- No backend required.

### Acceptance criteria

- Opens directly in browser.
- No console errors.
- Works with local sample data.

## Task 7 — Codex grant narrative assets

### Goal
Prepare project material that makes the Codex-assisted development story explicit.

### Files

- `docs/GRANT_BRIEF.md`
- README section: “Built with Codex-assisted development”

### Include

- Problem: saved web archives are messy and inaccessible to agents.
- Solution: local-first, Markdown-native source reef.
- Human-in-the-loop: Drift triage before agents build from sources.
- Codex role: implementation partner for importers, tests, UI, and refactors.
- Open-source value: reusable infrastructure for agent-readable personal archives.

### Acceptance criteria

- Clear 1-page grant brief.
- No exaggerated claims.
- Reflects actual current repo state.

## Task 7B — Mobile Review Mode prototype

### Goal
Create a mobile-first, browser-only static prototype for MemoReef Review Mode.

### Path

```text
site/swipe.html
```

### Requirements

- Show an import/session summary.
- Present one Drop card at a time.
- Support primary decisions:
  - Sink
  - Keep
  - Pearl
- Support escape actions:
  - Let agents finish
  - Continue later
- Encode the product principle: user taste where it matters, agent sorting everywhere else.
- Agents later assign category, tags, priority, note location, duplicate handling, and dead-link handling.
- Do not include a manual category picker.
- Keep it browser-only with no backend, external libraries, build tooling, or filesystem access.

### Acceptance criteria

- Opens directly with `open site/swipe.html`.
- Counters update when Sink, Keep, or Pearl is selected.
- Let agents finish and Continue later show clear static prototype states.
- Swipe gestures and visible buttons work for the main actions.

## Task 8 — Review session JSON bridge

### Goal
Connect local Markdown Drops to the static mobile Review Mode prototype without adding a backend.

### Requirements

- Add a CLI command that exports Drops to review-session JSON.
- Let Review Mode load review-session JSON with a browser file picker.
- Let Review Mode export decisions JSON from the browser.
- Keep the flow local-first and browser-only.
- Do not write decisions back to Markdown yet.
- Do not add a backend, external dependencies, or build tooling.

### Acceptance criteria

- `export-review-session --vault <vault>` writes a default JSON file under `MemoReef/review-sessions`.
- `--output` writes the review-session JSON to an explicit path.
- `site/swipe.html` keeps inline sample data as fallback.
- Loaded review sessions update counters and cards.
- Decision export downloads `memoreef-review-decisions.json`.
