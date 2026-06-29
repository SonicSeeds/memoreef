const ENDPOINT = 'http://127.0.0.1:8765/api/drop';
const extensionApi = globalThis.browser || globalThis.chrome;

const button = document.getElementById('drop-button');
const statusBox = document.getElementById('status');

function setStatus(message, kind = '') {
  statusBox.textContent = message;
  statusBox.dataset.kind = kind;
}

function callExtensionApi(fn, ...args) {
  const value = fn(...args);
  if (value && typeof value.then === 'function') {
    return value;
  }
  return new Promise((resolve, reject) => {
    fn(...args, result => {
      const runtimeError = extensionApi.runtime && extensionApi.runtime.lastError;
      if (runtimeError) {
        reject(new Error(runtimeError.message));
        return;
      }
      resolve(result);
    });
  });
}

async function getActiveTab() {
  const tabs = await callExtensionApi(extensionApi.tabs.query, { active: true, currentWindow: true });
  const tab = tabs && tabs[0];
  if (!tab || !tab.id || !tab.url) {
    throw new Error('No active browser tab found.');
  }
  if (!/^https?:\/\//i.test(tab.url)) {
    throw new Error('This browser page cannot be dropped. Open a normal http(s) page first.');
  }
  return tab;
}

async function getSelection(tabId) {
  const results = await callExtensionApi(extensionApi.scripting.executeScript, {
    target: { tabId },
    func: () => String(window.getSelection ? window.getSelection() : '').trim(),
  });
  const result = results && results[0];
  return String(result && result.result ? result.result : '').slice(0, 12000);
}

async function dropCurrentPage() {
  button.disabled = true;
  setStatus('Dropping into Reef…');
  try {
    if (!extensionApi || !extensionApi.tabs || !extensionApi.scripting) {
      throw new Error('Browser extension APIs are unavailable.');
    }
    const tab = await getActiveTab();
    const selection = await getSelection(tab.id);
    const response = await fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: tab.url,
        title: tab.title || tab.url,
        selection,
      }),
    });

    if (!response.ok) {
      throw new Error(`MemoReef returned HTTP ${response.status}.`);
    }

    const payload = await response.json();
    setStatus(payload.clipped ? 'Highlight clipped to Reef.' : 'Page dropped to Reef.', 'success');
  } catch (error) {
    setStatus(`${error.message}\n\nStart MemoReef with: memoreef serve --vault /path/to/vault`, 'error');
  } finally {
    button.disabled = false;
  }
}

button.addEventListener('click', dropCurrentPage);
