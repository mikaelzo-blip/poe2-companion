import { renderGearSlots, selectSlot } from './overview.js';
export { selectSlot };
import { fetchHttpRuntime } from './runtime.js';
import { SLOT_LABELS, addNotification, appState, esc, logToTerminal, showTransientNotification } from './state.js';

export function getCompareStorageKey() {
  const charId = appState.activeCharId || 'BOMSHAK';
  return `poe2_slot_compare_v2_${charId}`;
}

export function loadSlotCompareData() {
  try {
    const raw = localStorage.getItem(getCompareStorageKey());
    if (raw) {
      appState.slotCompareData = JSON.parse(raw);
    } else {
      appState.slotCompareData = {};
    }
  } catch (_) {
    appState.slotCompareData = {};
  }

  // Drop the hardcoded "Fate Core" demo seed that older versions persisted.
  const mh = appState.slotCompareData.main_hand;
  if (mh) {
    if (mh.history) mh.history = mh.history.filter(h => h.id !== 'cmp_seed_fate_core');
    if (mh.latestVerdict && mh.latestVerdict.item_name === 'Fate Core' && !mh.latestVerdict.evaluated_at) {
      mh.latestVerdict = null;
    }
  }
}

export function saveSlotCompareData() {
  try {
    localStorage.setItem(getCompareStorageKey(), JSON.stringify(appState.slotCompareData));
  } catch (_) {}
}

const ITEM_CLASS_TO_SLOT = {
  // main_hand
  'staves': 'main_hand',
  'staff': 'main_hand',
  'quarterstaves': 'main_hand',
  'quarterstaff': 'main_hand',
  'wands': 'main_hand',
  'wand': 'main_hand',
  'sceptres': 'main_hand',
  'sceptre': 'main_hand',
  'scepters': 'main_hand',
  'scepter': 'main_hand',
  'crossbows': 'main_hand',
  'crossbow': 'main_hand',
  'bows': 'main_hand',
  'bow': 'main_hand',
  'one hand maces': 'main_hand',
  'one hand mace': 'main_hand',
  'two hand maces': 'main_hand',
  'two hand mace': 'main_hand',
  'one hand swords': 'main_hand',
  'one hand sword': 'main_hand',
  'two hand swords': 'main_hand',
  'two hand sword': 'main_hand',
  'one hand axes': 'main_hand',
  'one hand axe': 'main_hand',
  'two hand axes': 'main_hand',
  'two hand axe': 'main_hand',
  'spears': 'main_hand',
  'spear': 'main_hand',
  'flails': 'main_hand',
  'flail': 'main_hand',
  'talismans': 'main_hand',
  'talisman': 'main_hand',
  'daggers': 'main_hand',
  'dagger': 'main_hand',
  'claws': 'main_hand',
  'claw': 'main_hand',

  // off_hand
  'foci': 'off_hand',
  'focus': 'off_hand',
  'shields': 'off_hand',
  'shield': 'off_hand',
  'bucklers': 'off_hand',
  'buckler': 'off_hand',
  'quivers': 'off_hand',
  'quiver': 'off_hand',

  // matching slots
  'rings': 'ring1',
  'ring': 'ring1',
  'amulets': 'amulet',
  'amulet': 'amulet',
  'belts': 'belt',
  'belt': 'belt',
  'helmets': 'helmet',
  'helmet': 'helmet',
  'helms': 'helmet',
  'helm': 'helmet',
  'gloves': 'gloves',
  'glove': 'gloves',
  'boots': 'boots',
  'boot': 'boots',
  'body armours': 'body_armour',
  'body armour': 'body_armour',
  'body armors': 'body_armour',
  'body armor': 'body_armour',
};

export function detectSlotFromItemText(rawText, fallbackSlot = null) {
  const lines = rawText.split('\n').map(l => l.trim().toLowerCase()).filter(Boolean);
  let itemClass = '';
  let baseType = '';

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (l.startsWith('item class:')) {
      itemClass = l.replace('item class:', '').trim();
    }
    if (l.startsWith('rarity:')) {
      if (lines[i + 2] && !lines[i + 2].startsWith('---')) {
        baseType = lines[i + 2].toLowerCase();
      }
    }
  }

  const slotFromClass = ITEM_CLASS_TO_SLOT[itemClass];
  if (slotFromClass) {
    if (slotFromClass === 'ring1') {
      if (fallbackSlot === 'ring2') return 'ring2';
      if (appState.loadout && appState.loadout.shared_slots) {
        const r1 = appState.loadout.shared_slots.ring1;
        const r2 = appState.loadout.shared_slots.ring2;
        if (r1 && r1.item && (!r2 || !r2.item)) {
          return 'ring2';
        }
      }
      return 'ring1';
    }
    if (slotFromClass === 'main_hand' && fallbackSlot === 'set2_main_hand') {
      return 'set2_main_hand';
    }
    if (slotFromClass === 'off_hand' && fallbackSlot === 'set2_off_hand') {
      return 'set2_off_hand';
    }
    return slotFromClass;
  }

  if (itemClass.includes('helmet') || itemClass.includes('helm') || baseType.includes('helm') || baseType.includes('circlet') || baseType.includes('crown')) {
    return 'helmet';
  }
  if (itemClass.includes('glove') || itemClass.includes('mitt') || baseType.includes('mitt') || baseType.includes('glove') || baseType.includes('gauntlet')) {
    return 'gloves';
  }
  if (itemClass.includes('boot') || itemClass.includes('greave') || baseType.includes('greave') || baseType.includes('sabatons') || baseType.includes('boot')) {
    return 'boots';
  }
  if (itemClass.includes('belt') || baseType.includes('belt') || baseType.includes('sash') || baseType.includes('cord') || baseType.includes('girdle')) {
    return 'belt';
  }
  if (itemClass.includes('amulet') || itemClass.includes('talisman') || baseType.includes('amulet') || baseType.includes('talisman') || baseType.includes('pendant') || baseType.includes('medallion')) {
    return 'amulet';
  }
  if (itemClass.includes('ring') || baseType.includes('ring') || baseType.includes('band') || baseType.includes('spiral')) {
    if (fallbackSlot === 'ring2') return 'ring2';
    if (appState.loadout && appState.loadout.shared_slots) {
      const r1 = appState.loadout.shared_slots.ring1;
      const r2 = appState.loadout.shared_slots.ring2;
      if (r1 && r1.item && (!r2 || !r2.item)) {
        return 'ring2';
      }
    }
    return 'ring1';
  }
  if (
    itemClass.includes('body armour') || itemClass.includes('body') || itemClass.includes('chest') ||
    baseType.includes('chestplate') || baseType.includes('vestment') || baseType.includes('armour') ||
    baseType.includes('mail') || baseType.includes('robe') || baseType.includes('tunic') ||
    baseType.includes('cuirass') || baseType.includes('plate') || baseType.includes('garb') ||
    baseType.includes('doublet')
  ) {
    return 'body_armour';
  }
  if (itemClass.includes('quiver') || itemClass.includes('shield') || baseType.includes('quiver') || baseType.includes('shield') || baseType.includes('buckler') || itemClass.includes('focus') || itemClass.includes('foci') || baseType.includes('focus')) {
    if (fallbackSlot === 'set2_off_hand') return 'set2_off_hand';
    return 'off_hand';
  }
  if (
    itemClass.includes('crossbow') || itemClass.includes('bow') || itemClass.includes('staff') ||
    itemClass.includes('wand') || itemClass.includes('sword') || itemClass.includes('axe') ||
    itemClass.includes('mace') || itemClass.includes('weapon') || itemClass.includes('sceptre') ||
    itemClass.includes('scepter') || itemClass.includes('flail') || itemClass.includes('spear') ||
    itemClass.includes('dagger') || itemClass.includes('claw') ||
    baseType.includes('crossbow') || baseType.includes('staff') || baseType.includes('quarterstaff') ||
    baseType.includes('spear') || baseType.includes('sceptre') || baseType.includes('flail') ||
    baseType.includes('dagger') || baseType.includes('claw')
  ) {
    if (fallbackSlot === 'set2_main_hand') return 'set2_main_hand';
    return 'main_hand';
  }

  return fallbackSlot || 'helmet';
}

export function recordSlotComparison(slotKey, rawText, data) {
  if (!slotKey) slotKey = 'helmet';
  if (!appState.slotCompareData[slotKey]) {
    appState.slotCompareData[slotKey] = { candidateText: '', latestVerdict: null, history: [] };
  }

  appState.slotCompareData[slotKey].candidateText = rawText;
  appState.slotCompareData[slotKey].latestVerdict = data;

  const historyItem = {
    id: 'cmp_' + Date.now() + '_' + Math.random().toString(36).substring(2, 6),
    timestamp: new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    slot: slotKey,
    slotLabel: SLOT_LABELS[slotKey] || slotKey.toUpperCase(),
    itemName: data.item_name || 'Candidate Item',
    baseType: data.base_type || '',
    rarity: (data.rarity || 'rare').toLowerCase(),
    verdict: data.verdict || 'EVALUATED',
    gains: data.gains || [],
    tradeOffs: data.trade_offs || [],
    rawText: rawText,
    verdictData: data
  };

  if (!Array.isArray(appState.slotCompareData[slotKey].history)) {
    appState.slotCompareData[slotKey].history = [];
  }
  const hist = appState.slotCompareData[slotKey].history;
  if (!hist.length || hist[0].rawText !== rawText || hist[0].verdict !== data.verdict) {
    hist.unshift(historyItem);
    if (hist.length > 25) hist.pop();

    const notifType = data.verdict === 'EQUIP_NOW' ? 'info' : (data.verdict === 'REJECT' ? 'warning' : 'info');
    const reasonSnippet = data.reason ? ` (${data.reason})` : '';
    addNotification(
      `Evaluasi ${historyItem.slotLabel}`,
      `${data.verdict || 'EVALUATED'}: ${historyItem.itemName}${reasonSnippet}`,
      notifType
    );
  }

  saveSlotCompareData();
}

export function getEquippedItemForSlot(slotKey) {
  if (!appState.loadout) return null;
  const shared = appState.loadout.shared_slots || {};
  const set1 = appState.loadout.weapon_set_1 || {};
  const set2 = appState.loadout.weapon_set_2 || {};

  const normKey = (slotKey || '').toLowerCase().trim();
  const directKey = normKey.replace(' ', '_');
  const compactKey = normKey.replace(' ', '').replace('_', '');

  let entry = shared[directKey] || shared[compactKey];
  if (!entry) {
    if (normKey.includes('set2') || normKey.includes('swap')) {
      entry = set2[directKey] || (normKey.includes('off') ? set2.off_hand : set2.main_hand);
    } else if (normKey.includes('weapon') || normKey.includes('main_hand') || normKey.includes('off_hand')) {
      entry = set1[directKey] || (normKey.includes('off') ? set1.off_hand : set1.main_hand);
    }
  }
  return entry && entry.item ? entry.item : null;
}

export function renderCompareForSlot(slotKey) {
  if (!slotKey) slotKey = appState.selectedSlot || 'helmet';
  const label = SLOT_LABELS[slotKey] || slotKey.toUpperCase();

  // 1. Target slot banner with equipped item name
  const titleEl = document.getElementById('compare-target-slot-title');
  const equippedItem = getEquippedItemForSlot(slotKey);
  const equippedDesc = equippedItem ? `${equippedItem.name || equippedItem.base_type}` : 'Slot Kosong';
  if (titleEl) {
    titleEl.innerHTML = `${esc(label.toUpperCase())} <span style="font-size: 11px; font-weight: 500; color: var(--accent-gold); margin-left: 8px;">[Terpasang: <strong>${esc(equippedDesc)}</strong>]</span>`;
  }

  const slotData = appState.slotCompareData[slotKey];
  const latestVerdict = slotData?.latestVerdict;

  // 2. Status badge
  const badgeEl = document.getElementById('compare-slot-status-badge');
  if (badgeEl) {
    if (!latestVerdict) {
      badgeEl.innerHTML = '<span class="badge-status-neutral">BELUM DIBANDINGKAN</span>';
    } else if (latestVerdict.verdict === 'EQUIP_NOW') {
      badgeEl.innerHTML = '<span class="badge-status-green">🟢 UPGRADE TERSEDIA</span>';
    } else if (latestVerdict.verdict === 'CONDITIONAL_UPGRADE') {
      badgeEl.innerHTML = '<span class="badge-status-gold">🟡 KONDISIONAL</span>';
    } else if (latestVerdict.verdict === 'REJECT') {
      badgeEl.innerHTML = '<span class="badge-status-red">🔴 UPGRADE DITOLAK</span>';
    } else {
      badgeEl.innerHTML = '<span class="badge-status-neutral">⚪ TERTUNDA</span>';
    }
  }

  // 3. Candidate textarea
  const textarea = document.getElementById('candidate-textarea');
  if (textarea) {
    textarea.value = slotData?.candidateText || '';
    textarea.placeholder = `Paste item kandidat untuk slot ${label.toUpperCase()} di sini (Ctrl+C di in-game lalu Ctrl+V)...`;
  }

  // 4. Comparison Result Container
  const resultContainer = document.getElementById('compare-verdict-result');
  if (resultContainer) {
    if (latestVerdict) {
      renderEvaluationVerdict(latestVerdict, resultContainer, slotKey);
    } else {
      resultContainer.style.display = 'block';
      resultContainer.innerHTML = `
        <div class="empty-state" style="padding: 24px 16px;">
          <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="12" y1="8" x2="12" y2="12"></line>
            <line x1="12" y1="16" x2="12.01" y2="16"></line>
          </svg>
          <div style="font-weight: 700; color: #FFF; margin-bottom: 4px;">Belum Ada Perbandingan untuk ${esc(label)}</div>
          <p style="font-size: 11px; color: var(--text-dim); max-width: 360px;">
            Arahkan kursor ke item ${esc(label)} di PoE2 lalu tekan <strong>Ctrl+C</strong> (Auto-Scan aktif), atau paste teks item di atas lalu klik Bandingkan.
          </p>
        </div>
      `;
    }
  }

  // 5. Render History
  renderCompareHistory();
}

export function renderCompareHistory() {
  const currentSlot = appState.selectedSlot || 'helmet';
  const filter = appState.historyFilter || 'slot';

  const slotCount = appState.slotCompareData[currentSlot]?.history?.length || 0;
  let allCount = 0;
  let allEntries = [];

  for (const [sk, sdata] of Object.entries(appState.slotCompareData)) {
    if (sdata && Array.isArray(sdata.history)) {
      allCount += sdata.history.length;
      allEntries.push(...sdata.history);
    }
  }

  const slotCountEl = document.getElementById('slot-history-count');
  if (slotCountEl) slotCountEl.textContent = slotCount;

  const allCountEl = document.getElementById('all-history-count');
  if (allCountEl) allCountEl.textContent = allCount;

  const listContainer = document.getElementById('compare-history-list');
  if (!listContainer) return;

  const entriesToDisplay = filter === 'slot'
    ? (appState.slotCompareData[currentSlot]?.history || [])
    : allEntries.sort((a, b) => (b.id > a.id ? 1 : -1));

  if (!entriesToDisplay.length) {
    listContainer.innerHTML = `
      <div style="text-align: center; padding: 18px 12px; color: var(--text-dim); font-size: 11px; font-family: var(--font-mono);">
        ${filter === 'slot' ? `Belum ada riwayat perbandingan untuk slot ${esc(SLOT_LABELS[currentSlot] || currentSlot)}.` : 'Belum ada riwayat perbandingan di seluruh loadout.'}
      </div>
    `;
    return;
  }

  listContainer.innerHTML = '';
  entriesToDisplay.forEach(item => {
    const card = document.createElement('div');
    card.className = 'history-card';

    const isEquip = item.verdict === 'EQUIP_NOW';
    const isConditional = item.verdict === 'CONDITIONAL_UPGRADE';
    const badgeClass = isEquip ? 'badge-green' : (isConditional ? 'badge-gold' : 'badge-red');

    let diffChipsHtml = '';
    if (item.gains && item.gains.length) {
      diffChipsHtml += item.gains.slice(0, 3).map(g => `<span class="diff-chip-gain">${esc(g)}</span>`).join('');
    }
    if (item.tradeOffs && item.tradeOffs.length) {
      diffChipsHtml += item.tradeOffs.slice(0, 2).map(t => `<span class="diff-chip-loss">${esc(t)}</span>`).join('');
    }

    card.innerHTML = `
      <div class="history-card-header">
        <div style="display: flex; align-items: center; gap: 6px;">
          <span class="history-slot-tag">${esc(item.slotLabel || item.slot.toUpperCase())}</span>
          <span class="history-time">${esc(item.timestamp)}</span>
        </div>
        <span class="verdict-badge ${badgeClass}" style="margin-bottom: 0; font-size: 9px; padding: 1px 6px;">${esc(item.verdict)}</span>
      </div>
      <div class="history-item-row">
        <div class="history-item-title">
          <span class="rarity-${esc(item.rarity || 'rare')}">${esc(item.itemName)}</span>
          <span class="history-item-base">${esc(item.baseType || '')}</span>
        </div>
      </div>
      ${diffChipsHtml ? `<div class="history-diff-chips">${diffChipsHtml}</div>` : ''}
      <div class="history-actions">
        <button class="btn-history-view" data-hist-id="${esc(item.id)}">Lihat Hasil</button>
        <button class="btn-history-del" data-hist-id="${esc(item.id)}" title="Hapus riwayat ini">✕</button>
      </div>
    `;

    // View button
    const btnView = card.querySelector('.btn-history-view');
    if (btnView) {
      btnView.addEventListener('click', (e) => {
        e.stopPropagation();
        if (item.slot && item.slot !== appState.selectedSlot) {
          selectSlot(item.slot);
        }
        const textarea = document.getElementById('candidate-textarea');
        if (textarea && item.rawText) {
          textarea.value = item.rawText;
        }
        const container = document.getElementById('compare-verdict-result');
        if (container && item.verdictData) {
          renderEvaluationVerdict(item.verdictData, container, item.slot);
          container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    }

    // Del button
    const btnDel = card.querySelector('.btn-history-del');
    if (btnDel) {
      btnDel.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteHistoryEntry(item.id, item.slot);
      });
    }

    listContainer.appendChild(card);
  });
}

export function deleteHistoryEntry(id, slotKey) {
  if (appState.slotCompareData[slotKey]?.history) {
    appState.slotCompareData[slotKey].history = appState.slotCompareData[slotKey].history.filter(h => h.id !== id);
    saveSlotCompareData();
    renderCompareHistory();
    if (appState.loadout) renderGearSlots(appState.loadout);
  }
}

export function setupCompareSubtabs() {
  loadSlotCompareData();

  const btnEquipped = document.getElementById('subtab-view-equipped');
  const btnCompare = document.getElementById('subtab-view-compare');
  const viewEquipped = document.getElementById('item-inspector-content');
  const viewCompare = document.getElementById('item-compare-content');

  if (btnEquipped && btnCompare) {
    btnEquipped.addEventListener('click', () => {
      btnEquipped.classList.add('active');
      btnCompare.classList.remove('active');
      viewEquipped.style.display = 'block';
      viewCompare.style.display = 'none';
    });

    btnCompare.addEventListener('click', () => {
      btnCompare.classList.add('active');
      btnEquipped.classList.remove('active');
      viewEquipped.style.display = 'none';
      viewCompare.style.display = 'block';
      renderCompareForSlot(appState.selectedSlot || 'helmet');
    });
  }

  // Paste from clipboard button
  const btnPaste = document.getElementById('btn-paste-clipboard');
  const textarea = document.getElementById('candidate-textarea');
  if (btnPaste && textarea) {
    btnPaste.addEventListener('click', async () => {
      let text = '';
      try {
        text = await navigator.clipboard.readText();
      } catch (_) {}

      // If browser clipboard API failed or returned empty, query local backend
      if (!text) {
        try {
          const res = await fetch('/api/get-clipboard');
          if (res.ok) {
            const data = await res.json();
            if (data && data.clipboard_text) {
              text = data.clipboard_text;
            }
          }
        } catch (_) {}
      }

      if (text && (text.includes('Rarity:') || text.includes('Item Class:'))) {
        const detectedSlot = detectSlotFromItemText(text, appState.selectedSlot);
        textarea.value = text;
        const resultContainer = document.getElementById('compare-verdict-result');
        if (resultContainer) {
          simulateVersusComparison(text, resultContainer, detectedSlot);
        }
      } else if (text) {
        textarea.value = text;
      } else {
        alert('Clipboard Windows kosong atau belum berisi item PoE2. Buka PoE2, arahkan kursor ke item, lalu tekan Ctrl+C.');
      }
    });
  }

  // Compare evaluation trigger
  const btnRunCompare = document.getElementById('btn-run-compare');
  const resultContainer = document.getElementById('compare-verdict-result');
  if (btnRunCompare && resultContainer) {
    btnRunCompare.addEventListener('click', () => {
      const text = textarea ? textarea.value.trim() : '';
      if (!text) {
        alert('Silakan copy atau paste item PoE2 terlebih dahulu.');
        return;
      }
      const targetSlot = detectSlotFromItemText(text, appState.selectedSlot);
      simulateVersusComparison(text, resultContainer, targetSlot);
    });
  }

  // History Filter Pills
  const filterSlot = document.getElementById('filter-history-slot');
  const filterAll = document.getElementById('filter-history-all');
  if (filterSlot && filterAll) {
    filterSlot.addEventListener('click', () => {
      appState.historyFilter = 'slot';
      filterSlot.classList.add('active');
      filterAll.classList.remove('active');
      renderCompareHistory();
    });
    filterAll.addEventListener('click', () => {
      appState.historyFilter = 'all';
      filterAll.classList.add('active');
      filterSlot.classList.remove('active');
      renderCompareHistory();
    });
  }

  // Clear History Button
  const btnClearHistory = document.getElementById('btn-clear-history');
  if (btnClearHistory) {
    btnClearHistory.addEventListener('click', () => {
      const currentSlot = appState.selectedSlot || 'helmet';
      const slotLabel = SLOT_LABELS[currentSlot] || currentSlot.toUpperCase();
      const isAll = appState.historyFilter === 'all';
      const promptText = isAll
        ? 'Hapus seluruh riwayat perbandingan di semua slot loadout?'
        : `Hapus riwayat perbandingan khusus untuk slot ${slotLabel}?`;

      if (confirm(promptText)) {
        if (isAll) {
          appState.slotCompareData = {};
        } else if (appState.slotCompareData[currentSlot]) {
          appState.slotCompareData[currentSlot].history = [];
          appState.slotCompareData[currentSlot].latestVerdict = null;
        }
        saveSlotCompareData();
        renderCompareForSlot(currentSlot);
        if (appState.loadout) renderGearSlots(appState.loadout);
      }
    });
  }

  // Initial render
  renderCompareForSlot(appState.selectedSlot || 'helmet');
}

export async function simulateVersusComparison(rawText, container, explicitSlot = null) {
  const lockCheckbox = document.getElementById('compare-lock-slot');
  const isLocked = Boolean(lockCheckbox && lockCheckbox.checked);

  if (isLocked && !appState.selectedSlot) {
    if (container) {
      container.style.display = 'block';
      container.innerHTML = `<div style="color: var(--accent-gold); font-size: 12px; font-family: var(--font-mono); padding: 12px;">Pilih slot dulu untuk mengunci.</div>`;
    }
    return;
  }

  const targetSlot = isLocked && appState.selectedSlot
    ? appState.selectedSlot
    : (explicitSlot || detectSlotFromItemText(rawText, appState.selectedSlot));
  const targetLabel = SLOT_LABELS[targetSlot] || (targetSlot ? targetSlot.toUpperCase() : 'SLOT');

  container.style.display = 'block';
  container.innerHTML = `<div style="color: var(--accent-gold); font-size: 12px; font-family: var(--font-mono); padding: 12px;">⏳ Mengevaluasi calon untuk slot ${esc(targetLabel)} dengan PoB2 & aturan guide...</div>`;

  const payload = {
    raw_text: rawText,
    character_id: appState.activeCharId || 'BOMSHAK',
  };
  if (isLocked && appState.selectedSlot) {
    payload.slot = appState.selectedSlot;
  }

  try {
    const res = await fetch('/api/evaluate-item', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const data = await res.json();
      if (data && data.error) {
        container.innerHTML = `
          <div class="verdict-box verdict-reject">
            <span class="verdict-badge badge-red">EVALUATION ERROR</span>
            <div class="verdict-details">${esc(data.error)}</div>
          </div>
        `;
        return;
      }

      data.raw_text = rawText;
      const slot = data.slot;
      if (!slot) {
        renderEvaluationVerdict(data, container);
        return;
      }

      recordSlotComparison(slot, rawText, data);
      logToTerminal('EVAL', `${data.item_name || 'Item'} (${slot}) -> ${data.verdict || 'OK'}`);

      if (appState.selectedSlot !== slot) {
        selectSlot(slot);
      } else {
        renderCompareForSlot(slot);
      }
      return;
    } else {
      let errorMsg = `Server error (${res.status})`;
      try {
        const errJson = await res.json();
        if (errJson && errJson.error) errorMsg = errJson.error;
      } catch (_) {}
      container.innerHTML = `
        <div class="verdict-box verdict-reject">
          <span class="verdict-badge badge-red">EVALUATION ERROR</span>
          <div class="verdict-details">${esc(errorMsg)}</div>
        </div>
      `;
      return;
    }
  } catch (err) {
    console.warn('Backend API evaluation failed:', err);
  }

  container.innerHTML = `
    <div class="verdict-box verdict-reject">
      <span class="verdict-badge badge-red">SERVER OFFLINE</span>
      <div class="verdict-details">Evaluasi butuh server. Jalankan <code>uv run python -m companion.cli dashboard</code> lalu buka dashboard dari URL yang ditampilkan.</div>
    </div>
  `;
}

export let autoScanInterval = null;

export function startAutoClipboardWatcher() {
  if (autoScanInterval) clearInterval(autoScanInterval);
  const toggle = document.getElementById('toggle-autoscan');
  const statusLabel = document.getElementById('autoscan-status-text');
  const toggleAutoEquip = document.getElementById('toggle-autoequip-empty');
  const autoEquipLabel = document.getElementById('autoequip-status-text');

  if (toggle) {
    toggle.addEventListener('change', () => {
      if (statusLabel) {
        statusLabel.innerHTML = toggle.checked
          ? '⚡ Auto-Scan Game Clipboard: <strong>AKTIF</strong>'
          : '⚡ Auto-Scan Game Clipboard: <span style="color: var(--text-dim);">NONAKTIF</span>';
      }
    });
  }

  if (toggleAutoEquip) {
    toggleAutoEquip.addEventListener('change', () => {
      if (autoEquipLabel) {
        autoEquipLabel.innerHTML = toggleAutoEquip.checked
          ? '🛡️ Auto-Pasang Slot Kosong: <strong>AKTIF</strong>'
          : '🛡️ Auto-Pasang Slot Kosong: <span style="color: var(--text-dim);">NONAKTIF</span>';
      }
    });
  }

  autoScanInterval = setInterval(async () => {
    if (toggle && !toggle.checked) return;

    try {
      const charId = appState.activeCharId || "BOMSHAK";
      const zoneParam = appState.currentZone ? `&zone=${encodeURIComponent(appState.currentZone)}` : '';
      const query = `?char_id=${encodeURIComponent(charId)}${zoneParam}`;

      const res = await fetch(`/api/clipboard-poll${query}`);
      if (res.ok) {
        const data = await res.json();
        if (data.has_new_item) {
          const slot = data.slot;
          if (!slot) {
            if (data.error && !data.error.includes("tidak bisa dipasang") && !data.error.includes("recognizable PoE2 item text")) {
              showTransientNotification(`⚠ Gagal evaluasi item: ${data.error}`);
            }
            return;
          }

          const toggleAutoEquip = document.getElementById('toggle-autoequip-empty');
          if (toggleAutoEquip && toggleAutoEquip.checked && data.auto_equip_ok) {
            // Auto equip item immediately!
            try {
              const equipRes = await fetch('/api/equip-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  raw_text: data.raw_text,
                  character_id: charId,
                  slot: slot
                })
              });
              if (equipRes.ok) {
                await fetchHttpRuntime();
                selectSlot(slot);
                showTransientNotification(`🛡️ Auto-Pasang: ${data.item_name || slot.toUpperCase()} berhasil dipasang ke loadout!`);
                logToTerminal('AUTOEQUIP', `${data.item_name || slot.toUpperCase()} dipasang ke slot ${slot}`);
                return;
              }
            } catch (_) {}
          }

          if (!data.timestamp) {
            data.timestamp = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
          }
          recordSlotComparison(slot, data.raw_text, data);
          const vsText = data.current_item_name ? ` vs ${data.current_item_name}` : '';
          showTransientNotification(`📋 Item Baru: ${data.item_name || slot.toUpperCase()}${vsText} (${data.verdict || 'EVALUATED'})`);
          logToTerminal('SCAN', `${data.item_name || 'Item'}${vsText} (${slot}) -> ${data.verdict || 'OK'}`);

          // Switch main navigation to Gear tab if not currently active
          const gearNav = document.querySelector('.nav-item[data-tab="tab-gear"]');
          if (gearNav && !gearNav.classList.contains('active')) {
            gearNav.click();
          }

          // Auto switch to Versus subtab if not already
          const btnCompare = document.getElementById('subtab-view-compare');
          const viewEquipped = document.getElementById('item-inspector-content');
          const viewCompare = document.getElementById('item-compare-content');
          const btnEquipped = document.getElementById('subtab-view-equipped');
          if (btnCompare && viewCompare) {
            btnCompare.classList.add('active');
            if (btnEquipped) btnEquipped.classList.remove('active');
            if (viewEquipped) viewEquipped.style.display = 'none';
            viewCompare.style.display = 'block';
          }

          // Select this slot so UI header, loadout grid, and compare panel align
          selectSlot(slot);
        }
      }
    } catch (_) {}
  }, 800);
}

export function formatPctDelta(v) {
  if (typeof v !== 'number' || isNaN(v)) return null;
  const pct = v * 100;
  const fixed = Math.abs(pct).toFixed(1);
  if (fixed === '0.0') {
    return '+0.0%';
  }
  return pct < 0 ? `−${fixed}%` : `+${fixed}%`;
}

export function renderEvaluationVerdict(data, container, targetSlot = null) {
  container.style.display = 'block';
  if (data.error) {
    container.innerHTML = `<div class="verdict-box verdict-reject"><span class="verdict-badge badge-red">PARSER ERROR</span><div class="verdict-details">${esc(data.error)}</div></div>`;
    return;
  }

  const currentSlot = targetSlot || data.slot || appState.selectedSlot || 'equipment';
  const isEquip = data.verdict === 'EQUIP_NOW';
  const isConditional = data.verdict === 'CONDITIONAL_UPGRADE';
  const isInsufficient = data.verdict === 'INSUFFICIENT_DATA';
  const badgeClass = isEquip ? 'badge-green' : (isConditional ? 'badge-gold' : (isInsufficient ? 'badge-gray' : 'badge-red'));
  const boxClass = isEquip ? 'verdict-equip-now' : (isConditional ? 'verdict-conditional' : (isInsufficient ? 'verdict-insufficient' : 'verdict-reject'));

  const effectiveSlot = data.slot || targetSlot || appState.selectedSlot || 'equipment';
  const slotLabel = (data.slot && SLOT_LABELS[data.slot]) || SLOT_LABELS[effectiveSlot] || effectiveSlot;
  const slotReasonPart = data.slot_reason ? ` — ${esc(data.slot_reason)}` : '';
  const slotBadgeHtml = `<div class="verdict-slot-line" style="font-size: 11px; color: var(--accent-gold); font-family: var(--font-mono); margin-bottom: 4px;">🎯 Slot: ${esc(slotLabel)}${slotReasonPart}</div>`;

  let deltasHtml = '';
  if ((data.engine === 'pob2' || data.engine === 'heuristic') && !isInsufficient && data.verdict !== 'ALREADY_EQUIPPED') {
    const dps = formatPctDelta(data.dps_pct);
    const ehp = formatPctDelta(data.ehp_pct);
    if (dps !== null && ehp !== null) {
      deltasHtml = `<div class="verdict-deltas" style="font-size: 12px; font-weight: 700; font-family: var(--font-mono); color: #f1f5f9; margin: 4px 0;">DPS ${dps} · EHP ${ehp}</div>`;
    }
  }

  let priorityHtml = '';
  if (data.guide && data.guide.priority_total) {
    const matched = Number(data.guide.priority_matched) || 0;
    const total = Number(data.guide.priority_total);
    const missingArr = Array.isArray(data.guide.must_have_missing) ? data.guide.must_have_missing.filter(Boolean) : [];
    const missingPart = missingArr.length > 0 ? ` (kurang: ${missingArr.map(m => esc(String(m))).join(', ')})` : '';
    priorityHtml = `<div class="verdict-priority-line" style="font-size: 11.5px; color: var(--accent-gold, #f59e0b); margin: 4px 0;">Prioritas guide ${matched}/${total}${missingPart}</div>`;
  }

  let targetFitHtml = '';
  const tf = data.guide?.target_fit || data.target_fit;
  if (tf && typeof tf === 'object') {
    const dpsVal = tf.dps_pct ?? tf.dps;
    const ehpVal = tf.ehp_pct ?? tf.ehp;
    const dps = formatPctDelta(dpsVal);
    const ehp = formatPctDelta(ehpVal);
    if (dps !== null && ehp !== null) {
      targetFitHtml = `<div class="verdict-target-fit" style="font-size: 11.5px; color: #94a3b8; font-family: var(--font-mono); margin: 4px 0;">Di build target: DPS ${dps} · EHP ${ehp}</div>`;
    }
  }

  let safetyBadgesHtml = '';
  if (Array.isArray(data.safety) && data.safety.length > 0) {
    safetyBadgesHtml = data.safety.map(reason => `
      <div class="verdict-safety-badge" style="background: rgba(239, 68, 68, 0.18); border: 1px solid var(--accent-red, #ef4444); color: #fca5a5; padding: 6px 12px; border-radius: 4px; font-size: 11.5px; font-weight: 600; margin: 4px 0;">⛔ ${esc(reason)}</div>
    `).join('');
  }

  let heuristicBadgeHtml = '';
  if (data.engine === 'heuristic') {
    const reasonSuffix = data.engine_reason ? ` — ${esc(data.engine_reason)}` : '';
    heuristicBadgeHtml = `<span title="PoB2 tidak tersedia / gagal; hasil dari estimasi stat lokal" style="font-size: 10.5px; font-family: var(--font-mono); color: #fbbf24; background: rgba(251,191,36,0.1); border: 1px solid rgba(251,191,36,0.4); padding: 2px 8px; border-radius: 4px;">⚠ Estimasi heuristik (tanpa PoB2)${reasonSuffix}</span>`;
  }

  let gainsHtml = '';
  if (data.gains && data.gains.length > 0) {
    gainsHtml = `<div style="margin-top: 6px; color: var(--accent-green);"><strong>Peningkatan (+):</strong><ul>${data.gains.map(g => `<li>${esc(g)}</li>`).join('')}</ul></div>`;
  }

  let tradeOffsHtml = '';
  if (data.trade_offs && data.trade_offs.length > 0) {
    tradeOffsHtml = `<div style="margin-top: 6px; color: var(--accent-red);"><strong>Penurunan / Trade-offs (-):</strong><ul>${data.trade_offs.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>`;
  }

  let tacticalCardHtml = '';
  if (data.tactical_advice) {
    const tac = data.tactical_advice;
    const badgeColor = tac.verdict === 'EQUIP_NOW' ? 'var(--accent-green)' : (tac.verdict === 'REJECT' ? 'var(--accent-red)' : 'var(--accent-gold)');
    tacticalCardHtml = `
      <div class="tactical-card">
        <div class="tactical-header">
          <span class="tactical-badge" style="color: ${badgeColor};">${esc(tac.verdict_badge || 'BRIEFING TAKTIS')}</span>
          <span class="tactical-zone">📍 ${esc(tac.zone_name || 'Zona Aktif')}</span>
        </div>
        <div class="tactical-headline">${esc(tac.tactical_headline || '')}</div>
        ${tac.zone_threat_warning ? `
          <div class="tactical-row threat-warning">
            <div class="tactical-label">⚠️ Ancaman Wilayah & Boss:</div>
            <div class="tactical-text">${esc(tac.zone_threat_warning)}</div>
          </div>
        ` : ''}
        ${tac.sustain_evaluation ? `
          <div class="tactical-row sustain-note">
            <div class="tactical-label">💚 Evaluasi Sustain:</div>
            <div class="tactical-text">${esc(tac.sustain_evaluation)}</div>
          </div>
        ` : ''}
        ${tac.attribute_warning ? `
          <div class="tactical-row attr-warning">
            <div class="tactical-label">🔴 Peringatan Syarat Atribut:</div>
            <div class="tactical-text">${esc(tac.attribute_warning)}</div>
          </div>
        ` : ''}
        ${tac.stat_analysis_notes && tac.stat_analysis_notes.length > 0 ? `
          <div class="tactical-row" style="background: rgba(30, 41, 59, 0.4); border-left: 3px solid #60a5fa; padding: 6px 10px; margin-top: 6px; border-radius: 4px;">
            <div class="tactical-label" style="color: #93c5fd; font-weight: 700; font-size: 11px;">📊 Analisis Stat Karakter Terhadap Item:</div>
            <ul style="margin: 4px 0 0 16px; padding: 0; font-size: 11px; color: #cbd5e1; line-height: 1.4;">
              ${tac.stat_analysis_notes.map(note => `<li>${esc(note)}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
        ${tac.actionable_recommendation ? `
          <div class="tactical-row action-box">
            <div class="tactical-label">🎯 Rekomendasi Taktis & Tindakan:</div>
            <div class="tactical-action-text">${esc(tac.actionable_recommendation)}</div>
          </div>
        ` : ''}
      </div>
    `;
  }

  let equipBtnHtml = '';
  let currentName = data.current_item_name || '';
  let currentBaseType = data.current_item_base_type || '';

  if (!currentName || currentName === 'Gear Lama' || currentName === 'Current Item') {
    const eq = getEquippedItemForSlot(currentSlot);
    if (eq) {
      currentName = eq.name || eq.base_type || 'Gear Terpasang';
      currentBaseType = currentBaseType || eq.base_type || '';
    } else {
      currentName = 'Slot Kosong';
    }
  }

  const candidateName = data.item_name || 'Item Baru';
  const candidateBaseType = data.base_type || '';

  const isWinnerCurrent = (data.verdict === 'REJECT');
  const isWinnerCandidate = isEquip;

  const currentOutcomeBadge = isWinnerCurrent
    ? '<span class="matchup-outcome-badge outcome-keep">👑 TAHAN (LEBIH BAGUS)</span>'
    : (isWinnerCandidate ? '<span class="matchup-outcome-badge outcome-reject">🔄 DIGANTIKAN</span>' : '');

  let candidateOutcomeBadge = '';
  if (isWinnerCandidate) {
    candidateOutcomeBadge = '<span class="matchup-outcome-badge outcome-equip">👑 PASANG (UPGRADE)</span>';
  } else if (isWinnerCurrent) {
    candidateOutcomeBadge = '<span class="matchup-outcome-badge outcome-reject">🛑 DITOLAK</span>';
  } else if (data.verdict === 'ALREADY_EQUIPPED') {
    candidateOutcomeBadge = '<span class="matchup-outcome-badge outcome-keep">✓ SUDAH TERPASANG</span>';
  } else if (data.verdict === 'INSUFFICIENT_DATA') {
    candidateOutcomeBadge = '<span class="matchup-outcome-badge outcome-keep">❓ DATA KURANG</span>';
  } else if (isConditional) {
    candidateOutcomeBadge = '<span class="matchup-outcome-badge outcome-keep">⚠️ KONDISIONAL</span>';
  }

  const matchupCardHtml = `
    <div class="compare-matchup-container">
      <div class="matchup-card current-gear ${isWinnerCurrent ? 'is-winner' : (isWinnerCandidate ? 'is-loser' : '')}">
        <div class="matchup-role-tag">🛡️ Terpasang (Current)</div>
        <div class="matchup-item-name">${esc(currentName)}</div>
        ${currentBaseType ? `<div class="matchup-base-type">(${esc(currentBaseType)})</div>` : ''}
        ${currentOutcomeBadge}
      </div>

      <div class="matchup-vs-divider">
        <div class="matchup-vs-circle">VS</div>
      </div>

      <div class="matchup-card candidate-gear ${isWinnerCandidate ? 'is-winner' : (isWinnerCurrent ? 'is-loser' : '')}">
        <div class="matchup-role-tag">📋 Kandidat (Candidate)</div>
        <div class="matchup-item-name">${esc(candidateName)}</div>
        ${candidateBaseType ? `<div class="matchup-base-type">(${esc(candidateBaseType)})</div>` : ''}
        ${candidateOutcomeBadge}
      </div>
    </div>
  `;

  if (currentSlot && data.raw_text) {
    if (isEquip) {
      equipBtnHtml = `
        <button class="btn btn-primary btn-block" id="btn-equip-candidate" style="margin-top: 12px; background: var(--accent-green); color: #000; font-weight: 700; cursor: pointer;">
          🛡️ Pasang ${esc(candidateName)} (Gantikan ${esc(currentName)})
        </button>
        <div id="equip-status-msg" style="margin-top: 6px; font-size: 11px; text-align: center; display: none;"></div>
      `;
    } else if (isConditional) {
      equipBtnHtml = `
        <button class="btn btn-primary btn-block" id="btn-equip-candidate" style="margin-top: 12px; background: var(--accent-gold); color: #000; font-weight: 700; cursor: pointer;">
          ⚠️ Pertahankan ${esc(currentName)} (Pasang ${esc(candidateName)} Hanya Jika Butuh Resistensi)
        </button>
        <div id="equip-status-msg" style="margin-top: 6px; font-size: 11px; text-align: center; display: none;"></div>
      `;
    } else if (data.verdict === 'REJECT') {
      equipBtnHtml = `
        <button class="btn btn-block" id="btn-equip-candidate" style="margin-top: 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid var(--accent-red); color: var(--accent-red); font-weight: 600; cursor: pointer; font-size: 11px;">
          🛑 Tahan ${esc(currentName)} (${esc(currentName)} LEBIH BAGUS — Jangan Pasang ${esc(candidateName)})
        </button>
        <div id="equip-status-msg" style="margin-top: 6px; font-size: 11px; text-align: center; display: none;"></div>
      `;
    }
  }

  const winnerBadgeHtml = (data.verdict === 'REJECT')
    ? `<div style="display: block; background: rgba(239, 68, 68, 0.18); border: 1px solid var(--accent-red); color: #ff9999; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 700; margin-bottom: 8px;">👑 KEPUTUSAN TEGAS: <u>${esc(currentName)}</u> LEBIH BAGUS DARI <u>${esc(candidateName)}</u></div>`
    : (isEquip ? `<div style="display: block; background: rgba(34, 197, 94, 0.18); border: 1px solid var(--accent-green); color: #86efac; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 700; margin-bottom: 8px;">👑 KEPUTUSAN TEGAS: <u>${esc(candidateName)}</u> LEBIH BAGUS DARI <u>${esc(currentName)}</u> (PASANG SEKARANG)</div>` : '');

  // Format freshness / evaluation timestamp
  let timeStr = data.timestamp || '';
  if (!timeStr && data.evaluated_at) {
    try {
      timeStr = new Date(data.evaluated_at).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (_) {
      timeStr = data.evaluated_at;
    }
  }
  if (!timeStr) {
    timeStr = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  const metaBarHtml = `
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 4px;">
      ${slotBadgeHtml}
      <span style="font-size: 10.5px; font-family: var(--font-mono); color: #94a3b8; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px;">
        🕒 Dievaluasi: <strong style="color: #f1f5f9;">${esc(timeStr)}</strong>
      </span>
      ${heuristicBadgeHtml}
    </div>
  `;

  const controllerTipHtml = `
    <div class="controller-tip-banner" style="background: rgba(15, 23, 42, 0.75); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 4px; padding: 6px 10px; margin-bottom: 10px; font-size: 11px; color: #cbd5e1; display: flex; align-items: center; justify-content: space-between; gap: 8px;">
      <div>🎮 <strong>Tips Stik / In-Game:</strong> Tombol stik tidak menyalin ke Windows. Tekan <code style="color: var(--accent-gold); background: rgba(0,0,0,0.6); padding: 2px 6px; border-radius: 3px; font-weight: bold; border: 1px solid rgba(255,255,255,0.1);">Ctrl+C</code> di game saat kursor di item untuk evaluasi otomatis.</div>
      <div style="color: var(--accent-green); font-size: 10px; font-weight: 700; white-space: nowrap;">● Auto-Scan Aktif</div>
    </div>
  `;

  // Avoid repeating the headline paragraph if tactical advice card is already rendering it
  const showGenericReason = !data.tactical_advice && data.reason;
  const reasonHtml = showGenericReason ? `<p style="margin-top: 6px; margin-bottom: 6px;">${esc(data.reason)}</p>` : '';

  const rawReportCollapsible = data.formatted_report ? `
    <details class="report-audit-details" style="margin-top: 10px; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 8px;">
      <summary style="cursor: pointer; font-size: 11px; color: var(--text-dim); font-family: var(--font-mono); user-select: none; outline: none;">
        ▶ 🔍 Detail Log Audit Teknis (PoB2 / CLI Raw Report)
      </summary>
      <pre class="report-raw-box" style="margin-top: 8px; font-size: 10.5px; opacity: 0.9; max-height: 220px; overflow-y: auto;">${esc(data.formatted_report)}</pre>
    </details>
  ` : '';

  container.innerHTML = `
    <div class="verdict-box ${boxClass}">
      <span class="verdict-badge ${badgeClass}">VERDICT: ${esc(data.verdict || '')}</span>
      <div class="verdict-details">
        ${metaBarHtml}
        ${controllerTipHtml}
        ${safetyBadgesHtml}
        ${winnerBadgeHtml}
        ${deltasHtml}
        ${priorityHtml}
        ${targetFitHtml}
        ${matchupCardHtml}
        ${reasonHtml}
        ${gainsHtml}
        ${tradeOffsHtml}
      </div>
      ${tacticalCardHtml}
      ${rawReportCollapsible}
      ${equipBtnHtml}
    </div>
  `;

  const btnEquip = container.querySelector('#btn-equip-candidate');
  const msgEl = container.querySelector('#equip-status-msg');
  if (btnEquip) {
    btnEquip.addEventListener('click', async () => {
      btnEquip.disabled = true;
      btnEquip.textContent = '⏳ Memasang ke loadout...';
      try {
        const res = await fetch('/api/equip-item', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            raw_text: data.raw_text,
            character_id: appState.activeCharId || "BOMSHAK",
            slot: currentSlot
          })
        });
        if (res.ok) {
          const resData = await res.json();
          if (resData.success) {
            if (msgEl) {
              msgEl.style.display = 'block';
              msgEl.style.color = 'var(--accent-green)';
              msgEl.textContent = '✓ ' + resData.message;
            }
            btnEquip.textContent = '✓ Terpasang!';
            addNotification('Loadout Diperbarui', resData.message || `Memasang ${data.item_name || 'item'} ke slot ${slotLabel}`, 'info');
            // Refresh live loadout on dashboard immediately
            fetchHttpRuntime();
            return;
          } else {
            alert(resData.error || 'Gagal update loadout');
          }
        } else {
          alert('Gagal menghubungi backend untuk update loadout');
        }
      } catch (err) {
        alert('Error: ' + err.message);
      }
      btnEquip.disabled = false;
      btnEquip.textContent = `🛡️ Pasang Item Ini ke Loadout (${slotLabel.toUpperCase()})`;
    });
  }
}
