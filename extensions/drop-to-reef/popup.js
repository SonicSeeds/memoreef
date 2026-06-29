const ENDPOINT = 'http://127.0.0.1:8765/api/drop';

const button = document.getElementById('drop-button');
const statusBox = document.getElementById('status');

function setStatus(message, kind = '') {
  statusBox.textContent = message;
  statusBox.dataset.kind = kind;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id || !tab.url) {
    throw new Error('No active browser tab found.');
  }
  if (!/^https?:\/\//i.test(tab.url)) {
    throw new Error('This browser page cannot be dropped. Open a normal http(s) page first.');
  }
  return tab;
}

async function getSelection(tabId) {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => String(window.getSelection ? window.getSelection() : '').trim(),
  });
  return String(result && result.result ? result.result : '').slice(0, 12000);
}

async function dropCurrentPage() {
  button.disabled = true;
  setStatus('Dropping into Reef…');
  try {
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
