import { startAutoClipboardWatcher } from './compare.js';
import { loadDataIntoUI } from './overview.js';
import { appState, updateStatusBadge } from './state.js';

export async function checkHttpHost() {
  if (window.location.protocol.startsWith('http')) {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json().catch(() => null);
        startHttpPolling(data);
        return;
      }
    } catch (_) {}
  }
  updateStatusBadge('SERVER OFFLINE', 'idle');
}

function applyEngineStatusBadge(engineStatus) {
  if (engineStatus && engineStatus.available === false && engineStatus.unavailable_reason) {
    updateStatusBadge(`PoB2 OFF: ${engineStatus.unavailable_reason}`, 'active');
  } else {
    updateStatusBadge('CONNECTED: HTTP LIVE', 'active');
  }
}

export function startHttpPolling(initialData = null) {
  applyEngineStatusBadge(initialData?.engine_status);
  fetchHttpRuntime();
  appState.pollTimer = setInterval(fetchHttpRuntime, 2000);

  // Poll clipboard automatically every 800ms
  startAutoClipboardWatcher();
}

export async function fetchHttpRuntime() {
  try {
    const charId = appState.activeCharId || 'BOMSHAK';
    const res = await fetch(`/api/status?char_id=${encodeURIComponent(charId)}`);
    if (res.ok) {
      const data = await res.json();
      applyEngineStatusBadge(data.engine_status);
      loadDataIntoUI(data.status, data.character, data.objective, data.loadout, data.baseline);
      document.getElementById('last-sync-time').textContent = 'Live Sync: ' + new Date().toLocaleTimeString();
      return;
    }
  } catch (err) {
    console.warn('HTTP API /api/status error:', err);
  }
  updateStatusBadge('DISCONNECTED', 'idle');
}


// Setup File System Access API
export function setupFolderAccess() {
  const btn = document.getElementById('btn-select-folder');
  const fallbackInput = document.getElementById('fallback-folder-input');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    // If showDirectoryPicker is supported (Chrome/Edge desktop)
    if ('showDirectoryPicker' in window) {
      try {
        const dirHandle = await window.showDirectoryPicker({
          id: 'poe2_runtime',
          mode: 'read'
        });
        appState.dirHandle = dirHandle;
        startLivePolling();
        return;
      } catch (err) {
        if (err.name === 'AbortError') return;
        console.warn('showDirectoryPicker failed, falling back to file input:', err);
      }
    }

    // Fallback: trigger input element for directory
    if (fallbackInput) {
      fallbackInput.click();
    }
  });

  if (fallbackInput) {
    fallbackInput.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files);
      if (!files.length) return;

      const fileMap = {};
      for (const f of files) {
        // relative path e.g. "runtime/runtime_status.json"
        const rel = f.webkitRelativePath || f.name;
        fileMap[rel] = f;
      }

      await parseUploadedFiles(fileMap);
      updateStatusBadge('CONNECTED: RUNTIME FOLDER', 'active');
      document.getElementById('last-sync-time').textContent = 'Loaded: ' + new Date().toLocaleTimeString();
    });
  }
}

export async function parseUploadedFiles(fileMap) {
  let statusJson = null;
  let objJson = null;
  let charJson = null;
  let loadoutJson = null;

  for (const [path, file] of Object.entries(fileMap)) {
    if (path.endsWith('runtime_status.json')) {
      try { statusJson = JSON.parse(await file.text()); } catch (_) {}
    } else if (path.endsWith('CURRENT_OBJECTIVE.json')) {
      try { objJson = JSON.parse(await file.text()); } catch (_) {}
    }
  }

  const charId = (statusJson && statusJson.active_character_id) || appState.activeCharId;
  for (const [path, file] of Object.entries(fileMap)) {
    if (path.includes(`characters/${charId}.json`) || path.includes(`characters\\${charId}.json`)) {
      try { charJson = JSON.parse(await file.text()); } catch (_) {}
    } else if (path.includes(`loadouts/${charId}.json`) || path.includes(`loadouts\\${charId}.json`)) {
      try { loadoutJson = JSON.parse(await file.text()); } catch (_) {}
    }
  }

  loadDataIntoUI(statusJson, charJson, objJson, loadoutJson);
}


// Setup Drag & Drop
export function setupDragAndDrop() {
  const overlay = document.getElementById('drag-drop-overlay');

  window.addEventListener('dragover', (e) => {
    e.preventDefault();
    overlay.classList.add('active');
  });

  window.addEventListener('dragleave', (e) => {
    if (e.relatedTarget === null) {
      overlay.classList.remove('active');
    }
  });

  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    overlay.classList.remove('active');

    const items = e.dataTransfer.items;
    if (items && items.length > 0) {
      const item = items[0];
      if (item.getAsFileSystemHandle) {
        const handle = await item.getAsFileSystemHandle();
        if (handle.kind === 'directory') {
          appState.dirHandle = handle;
          startLivePolling();
          return;
        }
      }
    }
    alert('Silakan drag folder /runtime dari proyek Anda.');
  });
}


// Live Polling
export function startLivePolling() {
  if (appState.pollTimer) clearInterval(appState.pollTimer);

  updateStatusBadge('CONNECTED: /runtime', 'active');
  readRuntimeFiles();

  // Poll every 2 seconds
  appState.pollTimer = setInterval(readRuntimeFiles, 2000);
}

export async function readRuntimeFiles() {
  if (!appState.dirHandle) return;

  try {
    let statusJson = null;
    let objJson = null;
    let charJson = null;
    let loadoutJson = null;

    // 1. Read runtime_status.json
    try {
      const statusFile = await appState.dirHandle.getFileHandle('runtime_status.json');
      const file = await statusFile.getFile();
      statusJson = JSON.parse(await file.text());
    } catch (_) {}

    // 2. Read CURRENT_OBJECTIVE.json
    try {
      const objFile = await appState.dirHandle.getFileHandle('CURRENT_OBJECTIVE.json');
      const file = await objFile.getFile();
      objJson = JSON.parse(await file.text());
    } catch (_) {}

    // 3. Read active character JSON
    const charId = (statusJson && statusJson.active_character_id) || appState.activeCharId;
    try {
      const charsDir = await appState.dirHandle.getDirectoryHandle('characters');
      const charFile = await charsDir.getFileHandle(`${charId}.json`);
      const file = await charFile.getFile();
      charJson = JSON.parse(await file.text());
    } catch (_) {}

    // 4. Read loadout JSON
    try {
      const loadoutsDir = await appState.dirHandle.getDirectoryHandle('loadouts');
      const loadoutFile = await loadoutsDir.getFileHandle(`${charId}.json`);
      const file = await loadoutFile.getFile();
      loadoutJson = JSON.parse(await file.text());
    } catch (_) {}

    loadDataIntoUI(statusJson, charJson, objJson, loadoutJson);
    document.getElementById('last-sync-time').textContent = 'Live Sync: ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.warn('Error reading runtime directory:', err);
    updateStatusBadge('ERROR READING FILES', 'idle');
  }
}
