import { fetchHttpRuntime } from './runtime.js';
import { appState, logToTerminal } from './state.js';
import { refreshTrackerIfVisible } from './tracker.js';

function fillSelect(sel, firstLabel, items, selected) {
  sel.innerHTML = '';
  [{ value: '', label: firstLabel }, ...items].forEach(it => {
    const opt = document.createElement('option');
    opt.value = it.value;
    opt.textContent = it.label;
    sel.appendChild(opt);
  });
  sel.value = items.some(i => i.value === selected) ? selected : '';
}

function showGuideError(msg) {
  const el = document.getElementById('guide-error');
  if (el) el.textContent = msg || '';
}

// Rebuild guide + stage dropdowns from stored guides and the character's stored assignment.
export async function refreshGuideControls() {
  const guideSelect = document.getElementById('guide-select');
  const stageSelect = document.getElementById('stage-select');
  if (!guideSelect || !stageSelect) return;
  try {
    const res = await fetch(`/api/guides?char_id=${encodeURIComponent(appState.activeCharId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const guides = data.guides || [];
    const active = data.active || {};
    fillSelect(guideSelect, 'Karakter saja', guides.map(g => ({ value: g.slug, label: g.name })), active.guide);
    const cur = guides.find(g => g.slug === guideSelect.value);
    fillSelect(stageSelect, 'Auto (berdasarkan level)',
      (cur ? cur.stages : []).map(st => ({ value: st.id, label: st.title })), active.stage_override);
    const tgt = document.getElementById('sb-build-target');
    const stg = document.getElementById('sb-build-stage');
    if (tgt) tgt.textContent = cur ? cur.name : 'Karakter saja';
    if (stg) stg.textContent = (cur && cur.stages.find(st => st.id === stageSelect.value)?.title) || 'Auto';
    showGuideError('');
  } catch (err) {
    console.warn('Failed to load guides:', err);
    showGuideError('Gagal memuat daftar guide');
  }
}

// Returns an error message, or null on success.
async function saveGuideAssignment(guide, stageOverride) {
  try {
    const res = await fetch('/api/character-guide', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_id: appState.activeCharId, guide: guide || null, stage_override: stageOverride || null })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.error) {
      return data.error || 'Gagal menyimpan guide';
    }
    return null;
  } catch (err) {
    return 'Gagal menghubungi API server';
  }
}

export async function setupCharacterAndGuideControls() {
  const charSelect = document.getElementById('header-char-select');
  const btnSync = document.getElementById('btn-quick-sync-char');
  const guideSelect = document.getElementById('guide-select');
  const stageSelect = document.getElementById('stage-select');

  // Load account characters
  try {
    const res = await fetch('/api/account-characters?account=mikaelzo%235674');
    if (res.ok) {
      const data = await res.json();
      if (charSelect && data.characters && data.characters.length > 0) {
        charSelect.innerHTML = '';
        data.characters.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c.name;
          opt.textContent = `${c.name} (Lvl ${c.level} ${c.ascendancy || c.class || 'Unknown'})`;
          if (c.name === (data.active_character_id || appState.activeCharId)) {
            opt.selected = true;
          }
          charSelect.appendChild(opt);
        });

        if (data.active_character_id) {
          appState.activeCharId = data.active_character_id;
        }
      }
    }
  } catch (err) {
    console.warn('Failed to load account characters:', err);
  }

  // Handle character switch
  if (charSelect) {
    charSelect.addEventListener('change', async () => {
      const selectedName = charSelect.value;
      if (!selectedName) return;

      const prevCharId = appState.activeCharId;
      try {
        const res = await fetch('/api/select-character', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: selectedName, account_name: 'mikaelzo#5674' })
        });
        if (res.ok) {
          appState.activeCharId = selectedName;
          showGuideError('');
          await refreshGuideControls();
          refreshTrackerIfVisible();
          logToTerminal('CHARACTER', `Karakter aktif beralih ke ${selectedName}`);
          await fetchHttpRuntime();
        } else {
          appState.activeCharId = prevCharId;
          if (prevCharId) charSelect.value = prevCharId;
          const data = await res.json().catch(() => ({}));
          const errMsg = data.error || `HTTP ${res.status}`;
          showGuideError(errMsg);
          logToTerminal('CHARACTER', `Gagal beralih karakter: ${errMsg}`);
        }
      } catch (err) {
        appState.activeCharId = prevCharId;
        if (prevCharId) charSelect.value = prevCharId;
        console.error('Failed to select character:', err);
        showGuideError(err.message || 'Gagal menghubungi API server');
      }
    });
  }

  // Handle quick sync button
  if (btnSync) {
    btnSync.addEventListener('click', async () => {
      const charId = appState.activeCharId || 'BOMSHAK';
      const acc = (document.getElementById('sync-account-name')?.value || '').trim() || 'mikaelzo#5674';
      const origText = btnSync.textContent;
      btnSync.textContent = '⏳...';
      btnSync.disabled = true;
      try {
        const res = await fetch('/api/fetch-public-profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: charId, account_name: acc, overwrite: true })
        });
        if (res.ok) {
          const resData = await res.json();
          if (resData.success) {
            alert(resData.message || `Berhasil menyinkronkan data untuk ${charId}!`);
            logToTerminal('SYNC', `Sinkronisasi profil selesai untuk ${charId}: ${resData.imported_slots || 0} slot diperbarui`);
            await fetchHttpRuntime();
          } else {
            alert(resData.message || resData.error || 'Gagal menyinkronkan data dari server PoE.');
            logToTerminal('SYNC', `Info sync: ${resData.error || 'Gagal menarik data'}`);
          }
        } else {
          alert('Gagal menyinkronkan data dari server PoE.');
        }
      } catch (err) {
        alert('Gagal menghubungi API server.');
      } finally {
        btnSync.textContent = origText;
        btnSync.disabled = false;
      }
    });
  }

  // Handle guide & stage selectors
  if (guideSelect) {
    guideSelect.addEventListener('change', async () => {
      const err = await saveGuideAssignment(guideSelect.value, null);
      await refreshGuideControls();
      if (err) showGuideError(err);
      await fetchHttpRuntime();
    });
  }

  if (stageSelect) {
    stageSelect.addEventListener('change', async () => {
      const err = await saveGuideAssignment(guideSelect?.value, stageSelect.value);
      await refreshGuideControls();
      showGuideError(err || '');
      await fetchHttpRuntime();
    });
  }

  await refreshGuideControls();
}
