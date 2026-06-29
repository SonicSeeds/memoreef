# Drop to Reef browser extension

Tiny WebExtension for saving the current page into a local MemoReef vault.

It posts to the existing local endpoint:

```text
http://127.0.0.1:8765/api/drop
```

## Run MemoReef first

```bash
memoreef serve --vault /path/to/vault
```

## Install in Chrome/Brave/Arc/Edge

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this folder:

```text
extensions/drop-to-reef
```

## Install temporarily in Firefox

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**.
3. Select this file:

```text
extensions/drop-to-reef/manifest.json
```

Temporary Firefox add-ons are removed when Firefox restarts. For persistent everyday Firefox use, the extension should be packaged and signed through Mozilla Add-ons or self-distribution.

## Use

1. Open a normal `http://` or `https://` page.
2. Optionally highlight text.
3. Click **Drop to Reef**.
4. Click **Drop current page**.

If text is highlighted, MemoReef saves it as a clipped selection. If nothing is highlighted, MemoReef saves the page URL/title as a normal Drop.

## Boundary

This extension does not sync, crawl, enrich, or store credentials. It is only a small local bridge from the active browser tab to your own `memoreef serve` process.
