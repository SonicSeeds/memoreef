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
- Swipe triage UI.
- Obsidian plugin.
- Browser extension.
- Agent search/index.

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

## Near-term roadmap

1. Robust browser bookmark import across Chrome/Brave/Arc/Firefox/Safari exports.
2. Broader dedupe controls and duplicate reporting across importer types.
3. `enrich` command for title refresh, metadata, summary placeholder, and dead-link checks.
4. `triage` data model: keep/archive/deep/project/pearl/discard.
5. Obsidian folder conventions and Dataview-friendly frontmatter.
6. Agent handoff format: project briefings generated from selected Drops/Shoals.
7. Optional UI: local web app or Tauri app for Drift triage.

## License

MIT, unless changed before public release.
