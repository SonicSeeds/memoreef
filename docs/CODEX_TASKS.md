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

## Task 9 — Apply review decisions to Markdown Drops

### Goal
Complete the local-first Review Mode loop by applying exported decision JSON back to Markdown Drop frontmatter.

### Requirements

- Add a CLI command that applies Review Mode decision JSON to Drops.
- Support a dry run before writing changes.
- Update `status`, `pearl`, and `triaged_at`.
- Prevent path traversal so decisions cannot modify files outside the vault Drops folder.
- Do not move or delete files.
- Do not assign categories, tags, priority, note locations, duplicate handling, or dead-link handling yet.

### Acceptance criteria

- `python3 -m memoreef.cli apply-review-decisions --vault <vault> --decisions <decisions.json>` updates Drop frontmatter.
- `--dry-run` reports the planned updates without modifying Markdown files.
- Missing files and malformed decisions produce warnings and continue.
- Path traversal attempts are skipped.
- Existing frontmatter fields and Markdown body are preserved.

## Task 10 — Agent finish plan for remaining Drops

### Goal
Create a structured local handoff for agents to finish sorting Drops after the user reviews a taste sample.

### Requirements

- Add a CLI command that writes an agent finish plan JSON.
- Include reviewed taste examples grouped by decision: pearl, keep, sink.
- Include remaining unreviewed Drops.
- Include concise agent instructions.
- Do not modify Markdown files.
- Do not classify remaining Drops yet.
- Do not add a backend, network calls, external dependencies, or LLM calls.

### Acceptance criteria

- `python3 -m memoreef.cli plan-agent-finish --vault <vault> --decisions <decisions.json>` writes a plan under `MemoReef/agent-plans`.
- `--output` writes the plan JSON to an explicit path.
- Missing files and malformed decisions produce warnings and continue.
- Reviewed Drops are excluded from `remaining_drops`.
- Markdown Drop files are not modified.

## Task 11 — Draft agent finish proposals

### Goal
Draft reviewable agent proposals for remaining Drops from an agent finish plan.

### Requirements

- Read an agent finish plan JSON.
- Draft proposals for remaining Drops.
- Include proposed status, pearl state, confidence, priority, suggested note location, rationale, and review flag.
- Use deterministic local token-overlap heuristics only.
- Preserve existing Drop tags as suggested tags; do not invent new tags.
- Do not modify Markdown files.
- Do not apply proposals yet.

### Acceptance criteria

- `python3 -m memoreef.cli draft-agent-proposals --plan <agent-finish-plan.json>` writes proposals next to the plan.
- `--output` writes the proposal JSON to an explicit path.
- Weak or tied signals remain `drift` and require user review.
- Pearl-like remaining Drops can be proposed as pearls.
- Sink-like remaining Drops can be proposed as discarded.
- Markdown Drop files are not modified.

## Task 12 — MemoReef v0.1 local app shell

### Goal
Make MemoReef feel like a usable local app by generating a static dashboard for the current vault.

### Requirements

- Add `python3 -m memoreef.cli app --vault <vault>`.
- Generate `<vault>/MemoReef/app/index.html`.
- Summarize total Drops, Drift, Reef, Pearls, and Discarded counts.
- Show the latest review session, review decisions, agent finish plan, and agent proposals when present.
- Show a clear next recommended action.
- Include local workflow instructions for Review Mode, applying decisions, creating a finish plan, and drafting proposals.
- Keep it static HTML with no backend, external dependencies, build tooling, or network calls.

### Acceptance criteria

- `python3 -m memoreef.cli app --vault <vault>` creates the dashboard.
- The dashboard handles empty vaults.
- The dashboard detects existing local review and proposal files.
- The dashboard contains Review Mode and Agent proposals guidance.
