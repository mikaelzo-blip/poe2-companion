import { fetchHttpRuntime } from './runtime.js';
import { appState, logToTerminal } from './state.js';

export const GUIDE_STAGES_MAP = {
  fubgun_flameblast: [
    { value: 'auto', label: 'Auto (Berdasarkan Level)' },
    { value: 'lvl 1-14', label: 'lvl 1-14' },
    { value: 'lvl 15-32', label: 'lvl 15-32' },
    { value: 'lvl 33-51', label: 'lvl 33-51' },
    { value: 'lvl 52 swap', label: 'lvl 52 Swap' },
    { value: 'lvl 53-68', label: 'lvl 53-68' },
    { value: 'lvl 85', label: 'lvl 85' },
    { value: 'endgame', label: 'Endgame' },
    { value: 'mageblood', label: 'Mageblood' },
    { value: 'dot cap', label: 'DoT Cap' }
  ],
  navira_varashta: [
    { value: 'auto', label: 'Auto (Berdasarkan Act/Level)' },
    { value: 'Act 1 & 2', label: 'Act 1 & 2 (Pre-Ascend)' },
    { value: 'Act 2', label: 'Act 2' },
    { value: 'Act 3', label: 'Act 3' },
    { value: 'Act 4 to Endgame', label: 'Act 4 to Endgame' },
    { value: 'Early Endgame', label: 'Early Endgame' },
    { value: 'Mid-Endgame', label: 'Mid-Endgame' },
    { value: 'Late Endgame', label: 'Late Endgame' },
    { value: 'Uber Endgame', label: 'Uber Endgame' }
  ],
  generic_pob2: [
    { value: 'auto', label: 'Auto (PoB2 Default)' }
  ]
};

export function refreshStageDropdown(guideId) {
  const stageSelect = document.getElementById('stage-select');
  if (!stageSelect) return;
  const stages = GUIDE_STAGES_MAP[guideId] || GUIDE_STAGES_MAP.generic_pob2;
  stageSelect.innerHTML = '';
  stages.forEach(st => {
    const opt = document.createElement('option');
    opt.value = st.value;
    opt.textContent = st.label;
    stageSelect.appendChild(opt);
  });
  appState.selectedStage = 'auto';
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
          opt.textContent = `${c.name} (Lvl ${c.level} ${c.class})`;
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

      appState.activeCharId = selectedName;
      try {
        const res = await fetch('/api/select-character', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: selectedName, account_name: 'mikaelzo#5674' })
        });
        if (res.ok) {
          const selectedText = charSelect.selectedOptions[0]?.textContent || '';
          if (guideSelect && selectedText.toLowerCase().includes('sorceress')) {
            guideSelect.value = 'navira_varashta';
            appState.selectedGuide = 'navira_varashta';
          } else if (guideSelect && selectedText.toLowerCase().includes('mercenary')) {
            guideSelect.value = 'fubgun_flameblast';
            appState.selectedGuide = 'fubgun_flameblast';
          } else if (guideSelect) {
            guideSelect.value = 'generic_pob2';
            appState.selectedGuide = 'generic_pob2';
          }
          refreshStageDropdown(appState.selectedGuide);
          const note = document.getElementById('guide-status-note');
          if (note && guideSelect) {
            note.textContent = `Aktif: ${guideSelect.selectedOptions[0]?.textContent || guideSelect.value}`;
          }
          logToTerminal('CHARACTER', `Karakter aktif beralih ke ${selectedName} (Guide: ${appState.selectedGuide})`);
          await fetchHttpRuntime();
        }
      } catch (err) {
        console.error('Failed to select character:', err);
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
    guideSelect.addEventListener('change', () => {
      appState.selectedGuide = guideSelect.value;
      refreshStageDropdown(appState.selectedGuide);
      const note = document.getElementById('guide-status-note');
      if (note) {
        note.textContent = `Aktif: ${guideSelect.selectedOptions[0]?.textContent || guideSelect.value}`;
      }
    });
  }

  if (stageSelect) {
    stageSelect.addEventListener('change', () => {
      appState.selectedStage = stageSelect.value;
    });
  }
}
