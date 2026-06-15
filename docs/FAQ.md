# MemoReef FAQ

## Is MemoReef local-first?

Yes. MemoReef runs on your machine and writes Markdown files into a local vault. The current MVP does not require an account, hosted backend, database, API key, or cloud sync.

## Does MemoReef require Obsidian?

No. MemoReef writes plain Markdown, so the files can be opened anywhere. Obsidian is a natural fit because MemoReef creates an Obsidian-ready folder structure, frontmatter, and graph-friendly hub links.

## Is MemoReef an AI summarizer?

Not primarily. MemoReef is a source library for saved links, bookmarks, notes, and future agent workflows. AI features can sit on top later, but the core is local import, review, search, and source organization.

## What are Drops, Drift, Reef, and Pearls?

- **Drops** are saved links or imported bookmarks.
- **Drift** is the unsorted inbox for new Drops.
- **Reef** is the reviewed source library.
- **Pearls** are high-value sources worth citing, revisiting, or handing to agents.

## Can agents use my sources?

Yes. MemoReef stores sources as structured Markdown with metadata, tags, status, and hub links. That makes the library easier for local agents to search, cite, and build on.

## What works today?

MemoReef can import browser bookmark exports, URL lists, and CSV files; generate Markdown Drops; run a local Review Mode app; autosave Keep/Pearl/Sink decisions; create reports; generate hub maps; and build a static local app view.

## What is not implemented yet?

Full article extraction, LLM summarization, deep semantic tagging, a browser extension, an Obsidian plugin, and hosted multi-device sync are not part of the current MVP.

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

## Does MemoReef send my bookmarks to an external service?

No. The current MVP performs local file operations. It does not send your bookmarks to a hosted MemoReef service.
