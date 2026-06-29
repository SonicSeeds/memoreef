const DEFAULT_SERVER_URL = 'http://127.0.0.1:8765';
const extensionApi = globalThis.browser || globalThis.chrome;

const button = document.getElementById('drop-button');
const statusBox = document.getElementById('status');
const serverUrlInput = document.getElementById('server-url');
const captureTokenInput = document.getElementById('capture-token');

function setStatus(message, kind = '') {
  statusBox.textContent = message;
  statusBox.dataset.kind = kind;
}

function storageGet(keys) {
  if (extensionApi.storage.local.get.length <= 1) {
    return extensionApi.storage.local.get(keys);
  }
  return new Promise(resolve => extensionApi.storage.local.get(keys, resolve));
}

function storageSet(values) {
  if (extensionApi.storage.local.set.length <= 1) {
    return extensionApi.storage.local.set(values);
  }
  return new Promise(resolve => extensionApi.storage.local.set(values, resolve));
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

function normalizeServerUrl(value) {
  const trimmed = String(value || '').trim().replace(/\/+$/, '');
  if (!trimmed) {
    return DEFAULT_SERVER_URL;
  }
  if (!/^http:\/\//i.test(trimmed)) {
    throw new Error('Use an http:// MemoReef URL, for example http://100.127.75.5:8765.');
  }
  return trimmed;
}

function dropEndpoint(serverUrl) {
  return `${serverUrl}/api/drop`;
}

async function loadSettings() {
  if (!extensionApi || !extensionApi.storage || !extensionApi.storage.local) {
    serverUrlInput.value = DEFAULT_SERVER_URL;
    return;
  }
  const stored = await storageGet({ serverUrl: DEFAULT_SERVER_URL, captureToken: '' });
  serverUrlInput.value = stored.serverUrl || DEFAULT_SERVER_URL;
  captureTokenInput.value = stored.captureToken || '';
}

async function saveSettings(serverUrl, captureToken) {
  if (!extensionApi || !extensionApi.storage || !extensionApi.storage.local) {
    return;
  }
  await storageSet({ serverUrl, captureToken });
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
    const serverUrl = normalizeServerUrl(serverUrlInput.value);
    const captureToken = captureTokenInput.value.trim();
    serverUrlInput.value = serverUrl;
    await saveSettings(serverUrl, captureToken);

    const tab = await getActiveTab();
    const selection = await getSelection(tab.id);
    const headers = { 'Content-Type': 'application/json' };
    if (captureToken) {
      headers.Authorization = `Bearer ${captureToken}`;
    }
    const response = await fetch(dropEndpoint(serverUrl), {
      method: 'POST',
      headers,
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
    setStatus(`${error.message}\n\nStart MemoReef with --lan on the Mac Mini and paste its URL + capture token here once.`, 'error');
  } finally {
    button.disabled = false;
  }
}

loadSettings().catch(error => setStatus(error.message, 'error'));
button.addEventListener('click', dropCurrentPage);
