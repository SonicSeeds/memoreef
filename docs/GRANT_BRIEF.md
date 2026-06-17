# MemoReef Grant Brief

## Project Summary

MemoReef is a local-first, Markdown-native source memory tool for people who save a lot of web material and want to turn it into useful project memory. The project imports browser bookmarks, plain URL lists, and CSV link exports into Obsidian-compatible Markdown Drops with metadata, provenance, triage state, and agent-readable structure. Over time, MemoReef is intended to become a private source reef where a user can import, review, retrieve, cite, and build from their own saved material.

MemoReef is also a practical artifact of Codex-assisted development. Tao/Hermes sets product direction, architecture, taste, verification, and repo orchestration. Codex helps implement focused, test-backed tasks such as importers, URL canonicalization, dedupe behavior, import logs, triage data fields, static UI prototypes, refactors, and documentation.

## Problem

People routinely save hundreds or thousands of links. Those links end up scattered across browser bookmark folders, read-later queues, note apps, social saves, newsletters, spreadsheets, and exported archives. The result is a pile of potentially valuable sources that is hard for a human to review and almost impossible for an agent to use reliably.

AI tools are strongest when they can work from grounded, user-owned context. But a messy saved-link archive is not grounded context yet. Bookmark titles are inconsistent, folders are stale, provenance is unclear, and weak sources sit next to important ones. Without structure and human review, an agent can easily overuse noisy material, miss important sources, or act on a giant archive that the user has never curated.

## Solution

MemoReef turns saved sources into local Markdown Drops. A Drop is a small, readable note representing a saved source. It includes core fields such as title, URL, type, status, agent readiness, pearl state, folders, tags, import source, and other frontmatter designed to work well in Obsidian and with future agent workflows.

The current CLI imports Netscape-style browser bookmark HTML, plain text URL lists, CSV files with title, URL, source, and tags, plus local PDFs, DOCX files, text files, Markdown documents, and OCR-assisted images/scanned PDFs through `import-docs`. It writes one Markdown file per source into an Obsidian-compatible vault structure. It also includes import inspection, URL canonicalization and dedupe behavior, import logs, document-text frontmatter, and triage-ready fields. These are early building blocks, but they establish the durable storage model and testing discipline needed for later enrichment, figure-aware visual understanding, and retrieval features.

## Why Local-First And Markdown-Native Matters

Saved sources are personal working memory. They can reveal a person's research interests, clients, plans, concerns, and private projects. MemoReef is designed to keep that material local by default and to avoid requiring a hosted backend for the MVP.

Markdown is a practical foundation because it is portable, inspectable, versionable, and already useful in tools like Obsidian. A user should be able to open a Drop as a normal note, understand what it contains, and move it without being locked into a service. For agent workflows, Markdown frontmatter gives future tools a stable way to read source metadata without depending on a proprietary database or hidden app state.

## Human-In-The-Loop Triage

MemoReef should not let agents blindly summarize or act on a giant messy archive. The Drift state is the inbox for imported Drops. Review Mode is the planned human triage layer where the user decides what matters before agents dive in.

The triage model is intentionally simple: keep useful sources in the Reef, mark high-value sources as Pearls, send long-term or uncertain material to the Deep, and discard weak material. This step protects the quality of future agent output. It also gives the user a fast way to convert old saved links into a curated library that reflects current priorities rather than historical clutter.

The repo already includes triage-ready frontmatter fields, a browser-only Review Mode fallback, and a local filesystem-backed Review Mode server. The local app loads Drift Drops from an Obsidian-compatible vault, lets the user sort with keyboard or button controls, autosaves Keep/Pearl/Sink decisions back to Markdown frontmatter, archives sunk Drops outside the active reef with a 30-day delete marker, and can tag kept/Pearl Drops locally after review. This turns human triage into immediate agent-readable structure without requiring a hosted account or external AI service.

## How Codex Is Being Used

MemoReef is being built through small, verifiable Codex tasks. Codex contributes implementation work in bounded areas: parser improvements, import commands, URL canonicalization, dedupe behavior, tests, import logs, triage data model changes, static UI prototypes, refactors, and documentation.

Tao/Hermes guides product intent, chooses scope, reviews tradeoffs, verifies behavior, and keeps the project honest about what is implemented. This division is important. Codex is not being used as an unsupervised product owner. It is an implementation partner inside a human-directed development loop, and MemoReef itself demonstrates that loop through its commit-sized tasks and acceptance criteria.

## Open-Source Value

MemoReef can become reusable local-first infrastructure for agent-readable personal archives. Builders, researchers, writers, consultants, and small teams all face the same pattern: important sources are saved over time, but they are difficult to reuse when starting a new project. A Markdown-native source reef can help them use their own saved material as grounded evidence for AI-assisted work without handing everything to another SaaS silo.

Open source matters here because the storage model, importers, triage conventions, and agent handoff formats should be inspectable and reusable. The project can provide a small, understandable foundation that others can adapt to their own vaults, workflows, and privacy needs.

## Current Status

Currently implemented: a Python CLI package, browser bookmark HTML import, plain URL list import, CSV link import, Obsidian-compatible Markdown Drops, Drift/Reef/Deep/Discarded/Pearl frontmatter fields, import inspection, import logs, a guided offline pilot command and checklist page, local Review Mode JSON export/application, filesystem-backed Review Mode autosave, phone triage over trusted LAN/Tailscale with a self-serve URL/QR workflow, Sink-to-Discarded archive lifecycle with 30-day delete markers, local reviewed-Drop tagging for kept/Pearl items, agent finish plans and deterministic proposals, duplicate/link/metadata/garden reports, library search, project brief export, a demo vault, a generated local dashboard/pilot/library/tour with Drop detail, review launcher, reports, and briefs pages, a static landing page, and browser-only triage prototypes.

Not implemented yet: full article extraction, LLM-generated summaries and deeper semantic tagging, an Obsidian plugin, a browser extension, a mobile app with vault sync, or a hosted sync/account layer.

## Next Milestones

The next milestones are to improve the quality and reviewability of local tagging/garden suggestions, add safer article extraction/summarization, refine generated project briefs from curated Drops, and document the storage conventions so other local-first tools can read and build on MemoReef vaults.
