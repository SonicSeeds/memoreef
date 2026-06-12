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

## Task 13 — Apply agent proposals to Markdown Drops

### Goal
Complete the local agent finish loop by applying accepted agent proposal JSON back to Drop frontmatter.

### Requirements

- Add `python3 -m memoreef.cli apply-agent-proposals --vault <vault> --proposals <agent-proposals.json>`.
- Support `--dry-run`.
- Skip proposals marked `requires_user_review: true` by default.
- Support `--include-needs-review` to apply those proposals deliberately.
- Update only `status`, `pearl`, `priority`, `note_location`, `agent_proposed_at`, and `agent_confidence`.
- Prevent path traversal.
- Do not move or delete files.
- Do not apply rationale into Markdown.
- Do not overwrite tags from `suggested_tags`.

### Acceptance criteria

- Accepted proposals update Markdown Drop frontmatter.
- Dry run reports proposed updates without modifying Markdown.
- Missing files, malformed proposals, invalid statuses, and path traversal warn and skip.
- Existing frontmatter fields and Markdown body are preserved.

## Task 14 — Duplicate report

### Goal
Create a local report that surfaces bookmark clutter without modifying Markdown files.

### Requirements

- Add `python3 -m memoreef.cli duplicate-report --vault <vault>`.
- Support `--output`; default to `<vault>/MemoReef/reports/YYYY-MM-DD-HHMMSS-duplicate-report.json`.
- Group exact canonical URL duplicates.
- Group same-domain clusters with at least two Drops.
- Group conservative similar-title matches.
- Do not modify, move, or delete Markdown files.
- Do not call network APIs.
- Update the local app dashboard to detect the latest duplicate report.

### Acceptance criteria

- Duplicate report JSON includes `summary`, `groups.exact_url`, `groups.same_domain`, and `groups.similar_title`.
- Singletons are excluded from duplicate groups.
- Empty or missing URLs do not crash.
- Dashboard includes latest duplicate report information.

## Task 15 — Dead-link checker

### Goal
Create a local report that helps users find broken or suspicious saved URLs before deeper review.

### Requirements

- Add `python3 -m memoreef.cli check-links --vault <vault>`.
- Support `--output`; default to `<vault>/MemoReef/reports/YYYY-MM-DD-HHMMSS-link-check-report.json`.
- Support `--timeout`, `--limit`, and `--method head|get|auto`.
- Use direct HTTP HEAD/GET requests against saved URLs only.
- Classify results as ok, broken, suspicious, or unknown.
- Do not modify, move, or delete Markdown files.
- Do not use third-party APIs or enrichment services.
- Update the local app dashboard to detect the latest link check report.

### Acceptance criteria

- Link check report JSON includes `summary`, `results`, and `warnings`.
- HTTP 200-range URLs are ok, 404/410 URLs are broken, and 401/403/429/500-range URLs are suspicious.
- Timeouts, connection errors, unsupported schemes, and malformed URLs do not crash.
- Dashboard includes latest link check report information.

## Task 16 — Metadata refresh

### Goal
Refresh basic page metadata from saved URLs before any AI enrichment.

### Requirements

- Add `python3 -m memoreef.cli refresh-metadata --vault <vault>`.
- Support `--dry-run`, `--limit`, and `--timeout`.
- Fetch saved URLs directly with HTTP GET only.
- Extract page title, description, canonical URL, and hostname.
- Update only metadata frontmatter fields.
- Do not move or delete files.
- Do not call third-party APIs or enrichment services.
- Preserve existing frontmatter fields and Markdown body.

### Acceptance criteria

- Metadata refresh writes `page_title`, `page_description`, `canonical_url`, `hostname`, `metadata_refreshed_at`, `metadata_status`, and `metadata_error`.
- Dry run reports planned updates without modifying Markdown files.
- Unsupported URLs and network errors warn without crashing.
- Dashboard includes `refresh-metadata` in the workflow.

## Task 17 — Project and shoal suggestions

### Goal
Create a local report that suggests existing project and shoal labels for unsorted Drops.

### Requirements

- Add `python3 -m memoreef.cli suggest-gardens --vault <vault>`.
- Support `--output`; default to `<vault>/MemoReef/reports/YYYY-MM-DD-HHMMSS-garden-suggestions.json`.
- Use Drops with existing `projects` or `shoals` as curated examples.
- Suggest only project and shoal labels already present in examples.
- Use deterministic local token-overlap heuristics.
- Do not modify, move, or delete Markdown files.
- Do not call network APIs.
- Update the local app dashboard to detect latest garden suggestions.

### Acceptance criteria

- Garden suggestion report JSON includes summary, suggestions, evidence tokens, and source examples.
- Drops with existing projects do not receive project suggestions.
- Drops with existing shoals do not receive shoal suggestions.
- If no examples exist, the report is valid and includes a warning.
- Dashboard includes latest garden suggestions information.

## Task 18 — Apply garden suggestions

### Goal
Apply accepted project and shoal suggestions from a garden suggestion report back to Markdown Drop frontmatter.

### Requirements

- Add `python3 -m memoreef.cli apply-garden-suggestions --vault <vault> --suggestions <garden-suggestions.json>`.
- Support `--accept-all`, repeatable `--accept-project`, repeatable `--accept-shoal`, and `--dry-run`.
- Return non-zero and do not modify files if no accept option is provided.
- Modify only `projects` and `shoals` frontmatter fields.
- Preserve Markdown body and all other frontmatter fields.
- Preserve existing labels and do not duplicate labels.
- Warn and continue for missing Drop paths or requested labels absent from the report.
- Do not move or delete files.
- Do not call network APIs.
- Include `apply-garden-suggestions` in the dashboard workflow.

### Acceptance criteria

- Accept-all applies suggested project and shoal labels.
- Selective accept applies only exact matching labels.
- Dry run reports planned updates without modifying Markdown.
- Missing files and unmatched requested labels produce warnings.
- Existing frontmatter fields and Markdown body are preserved.

## Task 19 — Filtered review sessions

### Goal
Create focused review queues by filtering Drops during review session export.

### Requirements

- Add filter options to `python3 -m memoreef.cli export-review-session`.
- Support repeatable `--project`, `--shoal`, `--status`, `--tag`, `--folder`, `--hostname`, and `--exclude-status`.
- Support `--pearl-only` and `--limit`.
- Match exact strings case-insensitively.
- AND different filter groups together and OR repeated values inside one group.
- Apply exclusions after inclusions and limit after filtering/sorting.
- Record filters in the review session JSON.
- Keep the command local-only and read-only.
- Mention filtered review export in the dashboard workflow.

### Acceptance criteria

- No filters preserve existing export behavior and write default filters.
- Project, shoal, status, tag, folder, hostname, pearl, exclusion, and limit filters work.
- CLI output includes a filter summary.
- README and task docs explain filtered review sessions.

## Task 20 — Library search

### Goal
Add a local Library/Search layer for finding useful Drops after import and review.

### Requirements

- Add `python3 -m memoreef.cli search-library --vault <vault> --query <text>`.
- Search local Markdown Drops only.
- Support the same main filters as filtered review sessions.
- Rank matches deterministically by title, labels, host/url, and body/summary matches.
- Write JSON search results under `MemoReef/search` by default.
- Keep the command read-only and local-only.
- Generate a static `MemoReef/app/library.html` page from `app`.
- Link or mention Library/Search from the app dashboard.

### Acceptance criteria

- Search results include query, filters, summary, ranked items, matched fields, scores, and snippets.
- Search can match title, body/summary, labels, hostname, and URL.
- Filters combine with search.
- `app` writes `library.html`.
- README and docs mention `search-library`.

## Task 22 — Generated product tour page

### Goal
Generate a static product tour page from the current vault data so a new user can open one page and understand why MemoReef is useful.

### Requirements

- Make `python3 -m memoreef.cli app --vault <vault>` generate `<vault>/MemoReef/app/tour.html`.
- Make `python3 -m memoreef.cli demo --output /tmp/memoreef-demo` produce the tour page too.
- Keep the tour static HTML with no backend, network, external dependencies, or build tooling.
- Generate the narrative from local vault data and existing local artifacts when present.
- Include sections for the mess, value, handoff, library, and why local Markdown matters.
- Link to `index.html`, `library.html`, and latest local review/report/search/agent JSON artifacts when detected.
- Do not claim unavailable features when related artifacts are missing.
- Link to `tour.html` from the dashboard.
- Point demo users to `MemoReef/app/tour.html` prominently.

### Acceptance criteria

- `app` writes `tour.html`.
- `index.html` links to `tour.html`.
- `demo` creates `MemoReef/app/tour.html`.
- The tour contains value narrative text and at least one real Drop title from demo/sample data.
- Existing tests still pass.

## Task 23 — Agent-ready project brief export

### Goal
Export selected local Markdown Drops into a readable Markdown project brief for agent or human handoff.

### Requirements

- Add `python3 -m memoreef.cli brief --vault <vault> --project "AI Agents"`.
- Support repeatable `--project`, `--shoal`, `--status`, `--tag`, and `--hostname`.
- Support `--pearl-only`, `--limit`, and optional `--output`.
- Write default briefs under `<vault>/MemoReef/briefs/YYYY-MM-DD-HHMMSS-project-brief.md`.
- Include generated timestamp, applied filters, summary counts, source metadata, source notes/summaries, Agent handoff instructions, and Gaps / next review.
- Keep the command local-only and read-only against Markdown Drops.
- Do not call network APIs, LLMs, external services, or add dependencies.
- Detect and link the latest project brief from the generated dashboard and tour.
- Make the demo command create a demo project brief.
- Update README and demo README text.

### Acceptance criteria

- Project-filtered brief generation works.
- Pearl-only, status, tag, and limit filters work together.
- Brief generation does not modify Drop Markdown files.
- Generated app and tour detect the latest brief.
- Demo creates a brief containing a real demo source title and Agent handoff text.
- Existing tests still pass.

## Task 24 — Generated app completion surface

### Goal
Turn the generated static app into a more complete local v0.2 app surface while preserving CLI-first workflows.

### Requirements

- Make `python3 -m memoreef.cli app --vault <vault>` generate one Drop detail page per Markdown Drop under `<vault>/MemoReef/app/drops/`.
- Add generated static pages for Review Mode instructions, local reports, and project briefs: `review.html`, `reports.html`, and `briefs.html`.
- Add simple app navigation across dashboard, tour, library, review, reports, and briefs.
- Link library and tour Drop references to generated Drop detail pages when possible.
- Keep the pages static, deterministic, local-only, and dependency-free.
- Do not claim that the generated static app can write review decisions directly to the filesystem.
- Make `demo` generate the expanded app surface and include enough local artifacts for review, reports, and briefs pages to be useful.
- Update README, demo README text, and grant status language if stale.

### Acceptance criteria

- `app` writes Drop detail pages, `review.html`, `reports.html`, and `briefs.html`.
- Library links at least one Drop detail page.
- Dashboard and tour navigation include review, reports, and briefs.
- Demo creates all new pages and at least one Drop detail page with a real demo title.
- Generated pages do not require network calls, external assets, external dependencies, or a backend.
- Existing tests still pass.
