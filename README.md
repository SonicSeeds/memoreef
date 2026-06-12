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
- **Deep**: searchable long-term archive, planned.
- **Pearls**: high-value sources, planned.
- **Shoals**: related source clusters, planned.
- **Dive**: search/agent retrieval, planned.

## Current MVP

Implemented:

- Parse Netscape-style browser bookmark HTML exports.
- Import plain text URL lists.
- Import CSV files with title, URL, source provenance, and tags.
- Preserve folder path as Markdown frontmatter.
- Write one Markdown file per bookmark.
- Store files in an Obsidian-ready folder structure.
- Mark imported items as `status: drift`, `agent_ready: true`, and triage-ready Drop frontmatter.

Not implemented yet:

- Article fetching/extraction.
- Automatic summaries and generated tags.
- Dead-link checking.
- Connected swipe Review Mode UI.
- Obsidian plugin.
- Browser extension.
- Agent search/index.

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

The agent proposals JSON suggests status, Pearl state, confidence, priority, note location, and rationale for each remaining Drop using deterministic local heuristics. It does not modify Markdown; applying proposals is a future task.

Generate the static local app dashboard:

```bash
python3 -m memoreef.cli app --vault /tmp/memoreef-vault
open /tmp/memoreef-vault/MemoReef/app/index.html
```

The dashboard summarizes Drop counts, shows the latest local review/agent artifacts, and points to the next recommended workflow step. It is static HTML and does not start a backend.

These are browser-only prototypes with inline sample data. They are not connected to real vault files yet.

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
