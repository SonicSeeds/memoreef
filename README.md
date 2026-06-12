# MemoReef

**Save sources. Let ideas surface.**

MemoReef imports browser bookmarks, plain URL lists, and simple CSV link exports into an Obsidian-compatible Markdown vault and turns saved links into an agent-readable source library for future projects.

This is an early MVP scaffold. The first useful path is intentionally simple:

```bash
python3 -m memoreef.cli import examples/bookmarks.html --vault /tmp/memoreef-vault
```

It can also import one-URL-per-line text files and CSV files with `title,url,source,tags` columns:

```bash
python3 -m memoreef.cli import-links links.txt --vault /tmp/memoreef-vault
python3 -m memoreef.cli import-csv links.csv --vault /tmp/memoreef-vault
```

It creates Markdown Drops under:

```text
/tmp/memoreef-vault/MemoReef/Drops/
```

## Product shape

MemoReef is not a generic bookmark manager. It is a local-first source reef:

- **Drops**: saved links or imported bookmarks.
- **Drift**: unsorted inbox state for new Drops.
- **Reef**: the living source library in Markdown/Obsidian.
- **Deep**: long-term archive state for saved sources.
- **Pearls**: high-value sources worth citing or reusing.
- **Shoals**: related source clusters.
- **Dive**: local search/library retrieval over saved Drops.

## Current MVP

Implemented:

- Parse Netscape-style browser bookmark HTML exports.
- Import plain text URL lists.
- Import CSV files with title, URL, source provenance, and tags.
- Preserve folder path as Markdown frontmatter.
- Write one Markdown file per bookmark.
- Store files in an Obsidian-ready folder structure.
- Mark imported items as `status: drift`, `agent_ready: true`, and triage-ready Drop frontmatter.
- Export and apply local Review Mode decisions.
- Generate agent finish plans and deterministic proposal drafts.
- Create duplicate, dead-link, metadata, garden suggestion, and library search reports.
- Generate a static local app with dashboard, library, and product tour pages.

Not implemented yet:

- Full article extraction/summarization.
- Automatic AI-generated tags or summaries.
- Browser extension.
- Obsidian plugin.
- Hosted sync or multi-device account layer.

## Built with Codex-assisted development

MemoReef is being built with focused Codex tasks that keep changes small, reviewable, and test-backed. Codex contributes implementation work such as importers, tests, UI prototypes, refactors, and documentation, while Tao/Hermes handles product direction, architecture, taste, verification, and repo orchestration.

See [docs/GRANT_BRIEF.md](docs/GRANT_BRIEF.md) for the grant-oriented project narrative.

## Example output

```markdown
---
title: "Local AI Agents for Small Teams"
url: "https://example.com/local-agents"
type: drop
status: drift
agent_ready: true
pearl: false
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
python3 -m memoreef.cli import examples/bookmarks.html --vault /tmp/memoreef-vault
find /tmp/memoreef-vault/MemoReef/Drops -type f
```

Run URL list or CSV imports:

```bash
python3 -m memoreef.cli import-links links.txt --vault /tmp/memoreef-vault
python3 -m memoreef.cli import-csv links.csv --vault /tmp/memoreef-vault
```

Open the static Drift triage prototype:

```bash
open site/triage.html
```

Open the mobile-first Review Mode prototype:

```bash
open site/swipe.html
```

Export a local review session JSON from a vault, then open the browser-only Review Mode and load the JSON with the file picker:

```bash
python3 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault
open site/swipe.html
```

Create filtered review sessions for focused queues:

```bash
python3 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --project "AI Agents"
python3 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --shoal "Automation"
python3 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --pearl-only
python3 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --status drift --exclude-status discarded
python3 -m memoreef.cli export-review-session --vault /tmp/memoreef-vault --status drift --limit 25
```

Filtered review sessions are local-only and do not modify files. Different filter groups combine together, while repeated values inside one group broaden that group.

Search your local library:

```bash
python3 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "agent workflow"
python3 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "workflow" --project "AI Agents"
python3 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "research" --pearl-only
python3 -m memoreef.cli search-library --vault /tmp/memoreef-vault --query "automation" --status drift --exclude-status discarded
```

Library search is local-only and read-only. It searches Markdown Drops and writes JSON results under `MemoReef/search` unless `--output` is provided.

Export selected Drops into a Markdown project brief:

```bash
python3 -m memoreef.cli brief --vault /tmp/memoreef-vault --project "AI Agents"
python3 -m memoreef.cli brief --vault /tmp/memoreef-vault --project "AI Agents" --pearl-only --limit 10
```

Project briefs are local-only and read-only against Drops. They write Markdown under `MemoReef/briefs/*-project-brief.md` unless `--output` is provided, include source URLs and Drop metadata, and add an Agent handoff section that tells an agent to use only listed sources, cite URLs, note gaps, and avoid invented claims.

Create a complete local demo vault:

```bash
python3 -m memoreef.cli demo --output /tmp/memoreef-demo
open /tmp/memoreef-demo/MemoReef/app/tour.html
open /tmp/memoreef-demo/MemoReef/app/index.html
```

The demo command writes fictional sample Drops and generates local review, duplicate, garden, search, project brief, agent-plan, product tour, Drop detail, review launcher, reports, briefs, and static app artifacts. Open `MemoReef/app/tour.html` first for the generated product story, then use the dashboard, library, review, reports, briefs, and example Drop detail pages. It does not use a backend, network call, AI call, or secrets.

Review Mode can export `memoreef-review-decisions.json` from the browser. The CLI can apply those decisions back to Markdown frontmatter.

Apply exported Review Mode decisions back to Markdown Drop frontmatter:

```bash
python3 -m memoreef.cli apply-review-decisions --vault /tmp/memoreef-vault --decisions /tmp/memoreef-review-decisions.json --dry-run
python3 -m memoreef.cli apply-review-decisions --vault /tmp/memoreef-vault --decisions /tmp/memoreef-review-decisions.json
```

This updates `status`, `pearl`, and `triaged_at` only. It does not move or delete files, and it does not assign categories, tags, priority, or note locations yet.

Create an agent finish plan for the remaining unreviewed Drops:

```bash
python3 -m memoreef.cli plan-agent-finish --vault /tmp/memoreef-vault --decisions /tmp/memoreef-review-decisions.json
```

The agent finish plan JSON groups reviewed taste examples into Pearl, Keep, and Sink, then lists the remaining Drops for a later agent task. It does not modify Markdown, and it does not classify the remaining Drops yet.

Draft agent proposals from an agent finish plan:

```bash
python3 -m memoreef.cli draft-agent-proposals --plan /tmp/agent-finish-plan.json
```

The agent proposals JSON suggests status, Pearl state, confidence, priority, note location, and rationale for each remaining Drop using deterministic local heuristics.

Apply accepted agent proposals back to Markdown Drop frontmatter:

```bash
python3 -m memoreef.cli apply-agent-proposals --vault /tmp/memoreef-vault --proposals /tmp/agent-proposals.json --dry-run
python3 -m memoreef.cli apply-agent-proposals --vault /tmp/memoreef-vault --proposals /tmp/agent-proposals.json
```

Proposals marked `requires_user_review: true` are skipped by default. Pass `--include-needs-review` to apply them deliberately. This updates frontmatter only and does not move, delete, or retag files.

Create a local duplicate report:

```bash
python3 -m memoreef.cli duplicate-report --vault /tmp/memoreef-vault
```

The duplicate report groups exact canonical URLs, same-domain clusters, and conservative similar-title matches. It is local-only, does not call the network, and does not modify, move, or delete files.

Check saved links directly:

```bash
python3 -m memoreef.cli check-links --vault /tmp/memoreef-vault --limit 100 --timeout 5
```

The link check report classifies saved URLs as ok, broken, suspicious, or unknown using direct HTTP HEAD/GET requests to the saved URLs only. It does not use third-party APIs and does not modify, move, or delete files.

Refresh basic page metadata:

```bash
python3 -m memoreef.cli refresh-metadata --vault /tmp/memoreef-vault --dry-run
python3 -m memoreef.cli refresh-metadata --vault /tmp/memoreef-vault --limit 50 --timeout 5
```

Metadata refresh fetches saved URLs directly, extracts page title, description, canonical URL, and hostname, then updates only the related frontmatter fields. It does not use third-party APIs and does not move, delete, or rewrite notes beyond those metadata fields.

Suggest projects and shoals from existing curated Drops:

```bash
python3 -m memoreef.cli suggest-gardens --vault /tmp/memoreef-vault
```

Garden suggestions are local-only heuristic reports. They compare unsorted Drops to Drops that already have projects or shoals, suggest only labels you already use, and do not modify, move, or delete files.

Apply accepted garden suggestions:

```bash
python3 -m memoreef.cli apply-garden-suggestions --vault /tmp/memoreef-vault --suggestions /tmp/garden-suggestions.json --dry-run --accept-all
python3 -m memoreef.cli apply-garden-suggestions --vault /tmp/memoreef-vault --suggestions /tmp/garden-suggestions.json --accept-project "AI Agents" --accept-shoal "Automation"
```

Applying garden suggestions only writes accepted project and shoal labels from a local suggestion report. It preserves existing labels, does not duplicate labels, and does not modify any other frontmatter fields or Markdown body.

Generate the static local app dashboard:

```bash
python3 -m memoreef.cli app --vault /tmp/memoreef-vault
open /tmp/memoreef-vault/MemoReef/app/tour.html
open /tmp/memoreef-vault/MemoReef/app/index.html
open /tmp/memoreef-vault/MemoReef/app/library.html
open /tmp/memoreef-vault/MemoReef/app/review.html
open /tmp/memoreef-vault/MemoReef/app/reports.html
open /tmp/memoreef-vault/MemoReef/app/briefs.html
```

The app command writes `index.html`, `tour.html`, `library.html`, `review.html`, `reports.html`, `briefs.html`, and one generated Drop detail page under `app/drops/` for each local Drop. The tour page is generated from local vault data and explains the product story: messy saves, useful Pearls, clutter reports, agent handoff artifacts, project briefs, library search, Drop detail pages, and why local Markdown matters. The dashboard summarizes Drop counts, shows the latest local review/agent/search/brief artifacts, links to the expanded app pages, and points to the next recommended workflow step. It is static HTML and does not start a backend.

The static site prototypes use inline sample data. The generated local app pages are created from real vault files and local JSON artifacts. None of them start a backend.

## Near-term roadmap

1. Robust browser bookmark import across Chrome/Brave/Arc/Firefox/Safari exports.
2. Broader dedupe controls and duplicate reporting across importer types.
3. `enrich` command for title refresh, metadata, summary placeholder, and dead-link checks.
4. Review Mode data model: sink/keep/pearl, let agents finish remaining, and continue sorting later.
5. Obsidian folder conventions and Dataview-friendly frontmatter.
6. Agent handoff format: project briefings generated from selected Drops/Shoals.
7. Optional UI: local web app or Tauri app for Drift triage.

## License

MIT, unless changed before public release.
