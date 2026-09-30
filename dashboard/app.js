/**
 * PoE2 Hermes Companion Suite - Client Application
 * Handles File System Access API, Drag-and-Drop, Live State Polling, & Demo Data.
 */

// Global State
const appState = {
  dirHandle: null,
  pollTimer: null,
  activeCharId: 'BOMSHAK',
  selectedGuide: 'fubgun_flameblast',
  selectedStage: 'auto',
  runtimeStatus: null,
  characterState: null,
  currentObjective: null,
  loadout: null,
  journeyLogs: [],
  selectedSlot: 'helmet',
  slotCompareData: {},
  historyFilter: 'slot' // 'slot' | 'all'
};

// Fallback Demo Data for instant zero-server preview
const DEMO_DATA = {
  status: {
    runtime_pid: 10256,
    lifecycle_state: "IDLE",
    session_id: "ebc78272344f4405aaac7023943c2bc1",
    game_process_running: true,
    game_pid: 14384,
    last_heartbeat: new Date().toISOString(),
    active_character_id: "BOMSHAK"
  },
  character: {
    character_id: "BOMSHAK",
    character_name: "BOMSHAK",
    character_class: "Mercenary",
    ascendancy: "Gemling Legionnaire",
    level: { value: 17, verification_state: "VERIFIED" },
    current_zone: { value: "G2_1", verification_state: "VERIFIED" },
    death_count: { value: 1, verification_state: "VERIFIED" },
    equipped_weapon_set: { value: 1 },
    build_progression: {
      active_stage: "lvl 1-14",
      target_build: "Fubgun 0.5.5 Flameblast Oil Grenade"
    },
    attributes: {
      strength: { value: 10 },
      dexterity: { value: 14 },
      intelligence: { value: 10 }
    }
  },
  objective: {
    primary_objective: {
      id: "passive:unknown:AscendancyMercenary3Notable1_#DEFAULT_OR_SHARED",
      priority: 5,
      title: "Audit Passive Tree: Ascendancy Notable",
      action: "Inspect passive tree to verify allocation of 'AscendancyMercenary3Notable1_'",
      rationale: "Passive observation incomplete: UNOBSERVED_SUBSYSTEM",
      source: "Passive Delta Evaluator",
      evidence_trust: 3,
      horizon: 1,
      cost_of_ignoring: 2,
      is_corrective: false
    },
    all_objectives: [
      {
        id: "passive:unknown:AscendancyMercenary3Notable1_#DEFAULT_OR_SHARED",
        priority: 5,
        title: "Audit Passive Tree: Ascendancy Notable",
        action: "Inspect passive tree to verify allocation of 'AscendancyMercenary3Notable1_'",
        source: "Passive Delta Evaluator",
        evidence_trust: 3,
        cost_of_ignoring: 2,
        is_corrective: false
      },
      {
        id: "passive:unknown:AscendancyMercenary3Notable4#DEFAULT_OR_SHARED",
        priority: 5,
        title: "Audit Passive Tree: Ascendancy Notable 4",
        action: "Inspect passive tree to verify allocation of 'AscendancyMercenary3Notable4'",
        source: "Passive Delta Evaluator",
        evidence_trust: 3,
        cost_of_ignoring: 2,
        is_corrective: false
      },
      {
        id: "gear:swap:flameblast_oil_grenade",
        priority: 4,
        title: "Prepare Lvl 52 Swap Gems",
        action: "Stash Flameblast and Oil Grenade uncut gems ready for milestone",
        source: "Transition Engine",
        evidence_trust: 4,
        cost_of_ignoring: 4,
        is_corrective: false
      }
    ]
  },
  loadout: {
    character_id: "BOMSHAK",
    revision: 1,
    is_finalized: false,
    shared_slots: {
      helmet: {
        item: {
          name: "Kraken Dome",
          base_type: "Rusted Greathelm",
          rarity: "rare",
          item_level: 8,
          required_level: 6,
          local_armour: 32,
          modifiers: [
            { raw_text: "10(6-13)% increased Armour" },
            { raw_text: "+10 to maximum Life" },
            { raw_text: "+9% to Fire Resistance" }
          ],
          advisor_notes: "Sesuai milestone Act 1. Pertahankan untuk resistensi api dasar sampai swap di Act 2."
        }
      },
      body_armour: {
        item: {
          name: "Iron Cuirass",
          base_type: "Chestplate",
          rarity: "magic",
          item_level: 12,
          required_level: 8,
          local_armour: 110,
          modifiers: [
            { raw_text: "+35 to maximum Life" },
            { raw_text: "+12% to Fire Resistance" }
          ],
          advisor_notes: "Prioritaskan flat life dan ketahanan elemental pada body armour selama Act 1-2."
        }
      },
      gloves: {
        item: {
          name: "Bramble Hand",
          base_type: "Iron Gauntlets",
          rarity: "magic",
          item_level: 7,
          required_level: 4,
          local_armour: 18,
          modifiers: [
            { raw_text: "+6 to Dexterity" },
            { raw_text: "+7% to Cold Resistance" }
          ],
          advisor_notes: "Cari sarung tangan dengan slot soket tambahan saat mencapai Lvl 20."
        }
      },
      boots: {
        item: {
          name: "Viper Tread",
          base_type: "Rawhide Boots",
          rarity: "magic",
          item_level: 9,
          required_level: 8,
          modifiers: [
            { raw_text: "10% increased Movement Speed" },
            { raw_text: "+12 to maximum Life" }
          ],
          advisor_notes: "Stat movement speed sangat penting untuk clear pace dan leveling."
        }
      },
      amulet: {
        item: {
          name: "Amber Amulet",
          base_type: "Amber Amulet",
          rarity: "magic",
          item_level: 10,
          required_level: 5,
          modifiers: [
            { raw_text: "+15 to Strength" },
            { raw_text: "+10 to maximum Life" }
          ],
          advisor_notes: "Berguna untuk memenuhi syarat atribut Strength pada equipment dan skill gem."
        }
      },
      ring1: {
        item: {
          name: "Iron Ring",
          base_type: "Iron Ring",
          rarity: "normal",
          item_level: 3,
          modifiers: [
            { raw_text: "Adds 1 to 4 Physical Damage to Attacks" }
          ],
          advisor_notes: "Ganti dengan Ruby Ring atau Sapphire Ring jika menghadapi boss resist elemental."
        }
      },
      ring2: {
        item: {
          name: "Gold Ring",
          base_type: "Gold Ring",
          rarity: "rare",
          item_level: 11,
          modifiers: [
            { raw_text: "+14% to Rarity of Items found" },
            { raw_text: "+8% to Lightning Resistance" }
          ],
          advisor_notes: "Membantu drop currency dan gold untuk persiapan respec level 52."
        }
      },
      belt: {
        item: {
          name: "Chain Belt",
          base_type: "Chain Belt",
          rarity: "magic",
          item_level: 10,
          modifiers: [
            { raw_text: "+15 to maximum Energy Shield" },
            { raw_text: "+14 to maximum Life" }
          ],
          advisor_notes: "Kombinasi life dan defensive buffer."
        }
      },
      main_hand: {
        item: {
          name: "Doom Stinger",
          base_type: "Repeating Crossbow",
          rarity: "rare",
          item_level: 12,
          modifiers: [
            { raw_text: "Adds 3 to 7 Physical Damage" },
            { raw_text: "Adds 2 to 5 Fire Damage" },
            { raw_text: "15% increased Attack Speed" }
          ],
          advisor_notes: "Senjata inti Weapon Set 1. Output attack speed tinggi memicu burst oil grenade lebih cepat."
        }
      }
    }
  }
};

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupFolderAccess();
  setupDragAndDrop();
  setupDemoButton();
  setupCompareSubtabs();
  setupSyncModal();
  await setupCharacterAndGuideControls();

  // Try auto-fetching via HTTP if hosted via server
  await checkHttpHost();
});

const SLOT_LABELS = {
  helmet: 'Helmet',
  body_armour: 'Body Armour',
  gloves: 'Gloves',
  boots: 'Boots',
  amulet: 'Amulet',
  ring1: 'Ring 1',
  ring2: 'Ring 2',
  belt: 'Belt',
  main_hand: 'Main Hand (Set 1)',
  off_hand: 'Off Hand (Set 1)',
  set2_main_hand: 'Main Hand (Set 2)',
  set2_off_hand: 'Off Hand (Set 2)'
};

const DEMO_CANDIDATES = {
  helmet: `Item Class: Helmets
Rarity: Rare
Kraken Crown
Soldier Greathelm
--------
Armour: 148
--------
Requirements:
Level: 16
Str: 25
--------
+35 to maximum Life
+18% to Fire Resistance
+14% to Lightning Resistance
+12 to Strength`,

  body_armour: `Item Class: Body Armours
Rarity: Rare
Dragon Carapace
Chestplate
--------
Armour: 198
--------
Requirements:
Level: 16
Str: 28
--------
+48 to maximum Life
+22% to Fire Resistance
+16% to Cold Resistance
+14 to Strength`,

  gloves: `Item Class: Gloves
Rarity: Rare
Rune Touch
Riveted Mitts
--------
Armour: 68
--------
Requirements:
Level: 15
Str: 18
--------
+24 to maximum Life
+15% to Cold Resistance
+12% to Fire Resistance
8% increased Attack Speed`,

  boots: `Item Class: Boots
Rarity: Rare
Brimstone Greaves
Iron Greaves
--------
Armour: 52
--------
Requirements:
Level: 14
Str: 12
--------
+16% to Fire Resistance
+14% to Cold Resistance
15% increased Movement Speed
+18 to maximum Life`,

  amulet: `Item Class: Amulets
Rarity: Rare
Beast Medallion
Amber Amulet
--------
Requirements:
Level: 14
--------
+18 to Strength (implicit)
--------
+28 to maximum Life
+15% to All Elemental Resistances
Adds 2 to 6 Physical Damage to Attacks`,

  ring1: `Item Class: Rings
Rarity: Rare
Doom Spiral
Iron Ring
--------
Requirements:
Level: 12
--------
Adds 1 to 4 Physical Damage to Attacks
+18 to maximum Life
+16% to Fire Resistance
+12% to All Elemental Resistances`,

  ring2: `Item Class: Rings
Rarity: Rare
Torment Band
Ruby Ring
--------
Requirements:
Level: 14
--------
+22% to Fire Resistance (implicit)
+25 to maximum Life
+14% to Lightning Resistance
+11% to Cold Resistance`,

  belt: `Item Class: Belts
Rarity: Rare
Viper Cord
Rawhide Belt
--------
Requirements:
Level: 15
--------
+32 to maximum Life
+18% to Cold Resistance
+15% to Lightning Resistance
+48 to Armour`,

  main_hand: `Item Class: Crossbows
Rarity: Rare
Fate Core
Varnished Crossbow
--------
Physical Damage: 20-59
Lightning Damage: 1-21
Critical Hit Chance: 5.00%
Attacks per Second: 1.60
Reload Time: 0.80
--------
Requirements:
Level: 16
Str: 19
Dex: 19
--------
64% increased Physical Damage
Adds 1 to 21 Lightning Damage
+94 to Accuracy Rating
+8 to Strength
Grants 2 Life per Enemy Hit
5% increased Light Radius`,

  off_hand: `Item Class: Quivers
Rarity: Rare
Gloom Flight
Broadhead Quiver
--------
Requirements:
Level: 14
--------
Adds 4 to 8 Physical Damage to Bow Attacks (implicit)
+28 to maximum Life
+14% to Fire Resistance
+12% to Cold Resistance`,

  set2_main_hand: `Item Class: Staves
Rarity: Rare
Blood Branch
Quarterstaff
--------
Physical Damage: 22-48
Critical Hit Chance: 6.50%
Attacks per Second: 1.30
--------
Requirements:
Level: 16
Dex: 22
Int: 22
--------
55% increased Physical Damage
Adds 5 to 15 Fire Damage
+22 to maximum Life`,

  set2_off_hand: `Item Class: Shields
Rarity: Rare
Aegis Ward
Spiked Shield
--------
Armour: 45
Evasion: 45
--------
Requirements:
Level: 15
--------
+25 to maximum Life
+16% to Lightning Resistance
+14% to Cold Resistance`
};

function getCompareStorageKey() {
  const charId = appState.activeCharId || 'BOMSHAK';
  return `poe2_slot_compare_v2_${charId}`;
}

function loadSlotCompareData() {
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

  // Pre-seed main_hand with Fate Core if slotCompareData is empty
  if (!appState.slotCompareData['main_hand']) {
    appState.slotCompareData['main_hand'] = {
      candidateText: DEMO_CANDIDATES.main_hand,
      latestVerdict: {
        item_name: "Fate Core",
        base_type: "Varnished Crossbow",
        slot: "main_hand",
        verdict: "EQUIP_NOW",
        reason: "Fubgun LEVELING_1_14 — Weapon 1: DPS upgrade without defensive trade-offs; PoB2 confirms the improvement.",
        gains: ["+11.61 DPS", "+16 Life", "+12.28 Total EHP"],
        trade_offs: [],
        formatted_report: "🟢 EQUIP NOW\nFate Core (Weapon 1) vs Dire Core\n+11.61 DPS\n+16 Life\n+12.28 Total EHP\nRecommendation: Fubgun LEVELING_1_14 — Weapon 1: DPS upgrade without defensive trade-offs; PoB2 confirms the improvement.",
        raw_text: DEMO_CANDIDATES.main_hand
      },
      history: [
        {
          id: 'cmp_seed_fate_core',
          timestamp: '01:17:42',
          slot: 'main_hand',
          slotLabel: 'Main Hand (Set 1)',
          itemName: 'Fate Core',
          baseType: 'Varnished Crossbow',
          rarity: 'rare',
          verdict: 'EQUIP_NOW',
          gains: ['+11.61 DPS', '+16 Life', '+12.28 Total EHP'],
          tradeOffs: [],
          rawText: DEMO_CANDIDATES.main_hand,
          verdictData: {
            item_name: "Fate Core",
            base_type: "Varnished Crossbow",
            slot: "main_hand",
            verdict: "EQUIP_NOW",
            reason: "Fubgun LEVELING_1_14 — Weapon 1: DPS upgrade without defensive trade-offs; PoB2 confirms the improvement.",
            gains: ["+11.61 DPS", "+16 Life", "+12.28 Total EHP"],
            trade_offs: [],
            formatted_report: "🟢 EQUIP NOW\nFate Core (Weapon 1) vs Dire Core\n+11.61 DPS\n+16 Life\n+12.28 Total EHP\nRecommendation: Fubgun LEVELING_1_14 — Weapon 1: DPS upgrade without defensive trade-offs; PoB2 confirms the improvement.",
            raw_text: DEMO_CANDIDATES.main_hand
          }
        }
      ]
    };
  }
}

function saveSlotCompareData() {
  try {
    localStorage.setItem(getCompareStorageKey(), JSON.stringify(appState.slotCompareData));
  } catch (_) {}
}

function detectSlotFromItemText(rawText, fallbackSlot = null) {
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
    itemClass.includes('mace') || itemClass.includes('weapon') || baseType.includes('crossbow') ||
    baseType.includes('staff') || baseType.includes('quarterstaff')
  ) {
    if (fallbackSlot === 'set2_main_hand') return 'set2_main_hand';
    return 'main_hand';
  }

  return fallbackSlot || 'helmet';
}

function recordSlotComparison(slotKey, rawText, data) {
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

function renderCompareForSlot(slotKey) {
  if (!slotKey) slotKey = appState.selectedSlot || 'helmet';
  const label = SLOT_LABELS[slotKey] || slotKey.toUpperCase();

  // 1. Target slot banner
  const titleEl = document.getElementById('compare-target-slot-title');
  if (titleEl) titleEl.textContent = label.toUpperCase();

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
          <div style="font-weight: 700; color: #FFF; margin-bottom: 4px;">Belum Ada Perbandingan untuk ${label}</div>
          <p style="font-size: 11px; color: var(--text-dim); max-width: 360px;">
            Arahkan kursor ke item ${label} di PoE2 lalu tekan <strong>Ctrl+C</strong> (Auto-Scan aktif), atau paste teks item di atas lalu klik Bandingkan.
          </p>
        </div>
      `;
    }
  }

  // 5. Render History
  renderCompareHistory();
}

function renderCompareHistory() {
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
        ${filter === 'slot' ? `Belum ada riwayat perbandingan untuk slot ${SLOT_LABELS[currentSlot] || currentSlot}.` : 'Belum ada riwayat perbandingan di seluruh loadout.'}
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
      diffChipsHtml += item.gains.slice(0, 3).map(g => `<span class="diff-chip-gain">${g}</span>`).join('');
    }
    if (item.tradeOffs && item.tradeOffs.length) {
      diffChipsHtml += item.tradeOffs.slice(0, 2).map(t => `<span class="diff-chip-loss">${t}</span>`).join('');
    }

    card.innerHTML = `
      <div class="history-card-header">
        <div style="display: flex; align-items: center; gap: 6px;">
          <span class="history-slot-tag">${item.slotLabel || item.slot.toUpperCase()}</span>
          <span class="history-time">${item.timestamp}</span>
        </div>
        <span class="verdict-badge ${badgeClass}" style="margin-bottom: 0; font-size: 9px; padding: 1px 6px;">${item.verdict}</span>
      </div>
      <div class="history-item-row">
        <div class="history-item-title">
          <span class="rarity-${item.rarity || 'rare'}">${item.itemName}</span>
          <span class="history-item-base">${item.baseType || ''}</span>
        </div>
      </div>
      ${diffChipsHtml ? `<div class="history-diff-chips">${diffChipsHtml}</div>` : ''}
      <div class="history-actions">
        <button class="btn-history-view" data-hist-id="${item.id}">Lihat Hasil</button>
        <button class="btn-history-del" data-hist-id="${item.id}" title="Hapus riwayat ini">✕</button>
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

function deleteHistoryEntry(id, slotKey) {
  if (appState.slotCompareData[slotKey]?.history) {
    appState.slotCompareData[slotKey].history = appState.slotCompareData[slotKey].history.filter(h => h.id !== id);
    saveSlotCompareData();
    renderCompareHistory();
    if (appState.loadout) renderGearSlots(appState.loadout);
  }
}

function setupCompareSubtabs() {
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

  // Context-aware Demo candidate button
  const btnDemoCandidate = document.getElementById('btn-demo-candidate');
  if (btnDemoCandidate && textarea) {
    btnDemoCandidate.addEventListener('click', () => {
      const activeSlot = appState.selectedSlot || 'helmet';
      textarea.value = DEMO_CANDIDATES[activeSlot] || DEMO_CANDIDATES['boots'];
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

function getEffectiveStage() {
  if (appState.selectedStage && appState.selectedStage !== "auto") {
    return appState.selectedStage;
  }
  const lvlObj = appState.characterState?.level;
  const lvl = (typeof lvlObj === 'object' ? lvlObj?.value : lvlObj)
    || appState.baseline?.character_level
    || 22;
  if (lvl >= 53) return "lvl 53-68";
  if (lvl >= 52) return "lvl 52 swap";
  if (lvl >= 33) return "lvl 33-51";
  if (lvl >= 15) return "lvl 15-32";
  return "lvl 1-14";
}

async function simulateVersusComparison(rawText, container, explicitSlot = null) {
  const targetSlot = explicitSlot || detectSlotFromItemText(rawText, appState.selectedSlot);
  const targetLabel = SLOT_LABELS[targetSlot] || targetSlot.toUpperCase();

  container.style.display = 'block';
  container.innerHTML = `<div style="color: var(--accent-gold); font-size: 12px; font-family: var(--font-mono); padding: 12px;">⏳ Mengevaluasi calon untuk slot ${targetLabel} dengan PoB2 Engine & Fubgun Rules...</div>`;

  try {
    const stage = getEffectiveStage();
    const guide = appState.selectedGuide || "fubgun_flameblast";
    const res = await fetch('/api/evaluate-item', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: rawText,
        character_id: appState.activeCharId || "BOMSHAK",
        stage: stage,
        guide: guide,
        slot: targetSlot
      })
    });

    if (res.ok) {
      const data = await res.json();
      data.raw_text = rawText;
      if (!data.slot) data.slot = targetSlot;

      recordSlotComparison(targetSlot, rawText, data);
      logToTerminal('EVAL', `${data.item_name || 'Item'} (${targetSlot}) -> ${data.verdict || 'OK'}`);

      if (appState.selectedSlot !== targetSlot) {
        selectSlot(targetSlot);
      } else {
        renderCompareForSlot(targetSlot);
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
          <div class="verdict-details">${errorMsg}</div>
        </div>
      `;
      return;
    }
  } catch (err) {
    console.warn('Backend API evaluation failed, attempting local fallback:', err);
  }

  // Graceful client-side fallback if backend is offline / file:// protocol
  runClientSideVersusFallback(rawText, container, targetSlot);
}

async function checkHttpHost() {
  if (window.location.protocol.startsWith('http')) {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        startHttpPolling();
        return;
      }
    } catch (_) {}

    try {
      const res = await fetch('/runtime/runtime_status.json');
      if (res.ok) {
        startHttpPolling();
        return;
      }
    } catch (_) {}
  }
  // Default to demo data if offline/file protocol
  loadDataIntoUI(DEMO_DATA.status, DEMO_DATA.character, DEMO_DATA.objective, DEMO_DATA.loadout);
  updateStatusBadge('DEMO / SIAP KONEK', 'idle');
}

function startHttpPolling() {
  updateStatusBadge('CONNECTED: HTTP LIVE', 'active');
  fetchHttpRuntime();
  appState.pollTimer = setInterval(fetchHttpRuntime, 2000);

  // Poll clipboard automatically every 800ms
  startAutoClipboardWatcher();
}

let logEventCount = 0;
function logToTerminal(category, message) {
  const term = document.getElementById('terminal-output');
  const watermark = document.getElementById('log-watermark');
  if (term) {
    const line = document.createElement('div');
    line.className = 'log-line';
    const time = new Date().toLocaleTimeString();
    line.textContent = `[${category.toUpperCase()}] ${time} : ${message}`;
    term.appendChild(line);
    term.scrollTop = term.scrollHeight;
    logEventCount++;
    if (watermark) {
      watermark.textContent = `Events: ${logEventCount}`;
    }
  }
}

let autoScanInterval = null;
function startAutoClipboardWatcher() {
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
      const stage = getEffectiveStage();
      const guide = appState.selectedGuide || "fubgun_flameblast";
      const query = `?char_id=${encodeURIComponent(charId)}&stage=${encodeURIComponent(stage)}&guide=${encodeURIComponent(guide)}`;

      const res = await fetch(`/api/clipboard-poll${query}`);
      if (res.ok) {
        const data = await res.json();
        if (data.has_new_item) {
          const targetSlot = detectSlotFromItemText(data.raw_text, appState.selectedSlot);
          data.slot = targetSlot;

          // Check if target slot is currently empty/unassigned in loadout
          let isSlotEmpty = true;
          if (appState.loadout) {
            const sharedSlots = appState.loadout.shared_slots || {};
            const weaponSet1 = appState.loadout.weapon_set_1 || {};
            const weaponSet2 = appState.loadout.weapon_set_2 || {};
            if (targetSlot === 'main_hand') isSlotEmpty = !(weaponSet1.main_hand?.item || sharedSlots.main_hand?.item);
            else if (targetSlot === 'off_hand') isSlotEmpty = !(weaponSet1.off_hand?.item || sharedSlots.off_hand?.item);
            else if (targetSlot === 'set2_main_hand') isSlotEmpty = !weaponSet2.main_hand?.item;
            else if (targetSlot === 'set2_off_hand') isSlotEmpty = !weaponSet2.off_hand?.item;
            else isSlotEmpty = !sharedSlots[targetSlot]?.item;
          }

          const toggleAutoEquip = document.getElementById('toggle-autoequip-empty');
          if (isSlotEmpty && toggleAutoEquip && toggleAutoEquip.checked) {
            // Auto equip item to empty slot immediately!
            try {
              const equipRes = await fetch('/api/equip-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  raw_text: data.raw_text,
                  character_id: charId,
                  slot: targetSlot
                })
              });
              if (equipRes.ok) {
                await fetchHttpRuntime();
                selectSlot(targetSlot);
                showTransientNotification(`🛡️ Auto-Pasang: ${data.item_name || targetSlot.toUpperCase()} berhasil dipasang ke loadout!`);
                logToTerminal('AUTOEQUIP', `${data.item_name || targetSlot.toUpperCase()} dipasang ke slot ${targetSlot}`);
                return;
              }
            } catch (_) {}
          }

          recordSlotComparison(targetSlot, data.raw_text, data);
          logToTerminal('SCAN', `${data.item_name || 'Item'} (${targetSlot}) -> ${data.verdict || 'OK'}`);

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
          selectSlot(targetSlot);
        }
      }
    } catch (_) {}
  }, 800);
}

function renderEvaluationVerdict(data, container, targetSlot = null) {
  container.style.display = 'block';
  if (data.error) {
    container.innerHTML = `<div class="verdict-box verdict-reject"><span class="verdict-badge badge-red">PARSER ERROR</span><div class="verdict-details">${data.error}</div></div>`;
    return;
  }

  const currentSlot = targetSlot || data.slot || appState.selectedSlot || 'equipment';
  const isEquip = data.verdict === 'EQUIP_NOW';
  const isConditional = data.verdict === 'CONDITIONAL_UPGRADE';
  const isInsufficient = data.verdict === 'INSUFFICIENT_DATA';
  const badgeClass = isEquip ? 'badge-green' : (isConditional ? 'badge-gold' : (isInsufficient ? 'badge-gray' : 'badge-red'));
  const boxClass = isEquip ? 'verdict-equip-now' : (isConditional ? 'verdict-conditional' : (isInsufficient ? 'verdict-insufficient' : 'verdict-reject'));

  const slotLabel = SLOT_LABELS[currentSlot] || currentSlot.toUpperCase().replace('_', ' ');
  const slotBadgeHtml = `<div style="font-size: 11px; color: var(--accent-gold); font-family: var(--font-mono); margin-bottom: 4px;">🎯 Slot Evaluasi: ${slotLabel.toUpperCase()}</div>`;

  let gainsHtml = '';
  if (data.gains && data.gains.length > 0) {
    gainsHtml = `<div style="margin-top: 6px; color: var(--accent-green);"><strong>Peningkatan (+):</strong><ul>${data.gains.map(g => `<li>${g}</li>`).join('')}</ul></div>`;
  }

  let tradeOffsHtml = '';
  if (data.trade_offs && data.trade_offs.length > 0) {
    tradeOffsHtml = `<div style="margin-top: 6px; color: var(--accent-red);"><strong>Penurunan / Trade-offs (-):</strong><ul>${data.trade_offs.map(t => `<li>${t}</li>`).join('')}</ul></div>`;
  }

  let tacticalCardHtml = '';
  if (data.tactical_advice) {
    const tac = data.tactical_advice;
    const badgeColor = tac.verdict === 'EQUIP_NOW' ? 'var(--accent-green)' : (tac.verdict === 'REJECT' ? 'var(--accent-red)' : 'var(--accent-gold)');
    tacticalCardHtml = `
      <div class="tactical-card">
        <div class="tactical-header">
          <span class="tactical-badge" style="color: ${badgeColor};">${tac.verdict_badge || 'BRIEFING TAKTIS'}</span>
          <span class="tactical-zone">📍 ${tac.zone_name || 'Zona Aktif'}</span>
        </div>
        <div class="tactical-headline">${tac.tactical_headline || ''}</div>
        ${tac.zone_threat_warning ? `
          <div class="tactical-row threat-warning">
            <div class="tactical-label">⚠️ Ancaman Wilayah & Boss:</div>
            <div class="tactical-text">${tac.zone_threat_warning}</div>
          </div>
        ` : ''}
        ${tac.sustain_evaluation ? `
          <div class="tactical-row sustain-note">
            <div class="tactical-label">💚 Evaluasi Sustain:</div>
            <div class="tactical-text">${tac.sustain_evaluation}</div>
          </div>
        ` : ''}
        ${tac.attribute_warning ? `
          <div class="tactical-row attr-warning">
            <div class="tactical-label">🔴 Peringatan Syarat Atribut:</div>
            <div class="tactical-text">${tac.attribute_warning}</div>
          </div>
        ` : ''}
        ${tac.actionable_recommendation ? `
          <div class="tactical-row action-box">
            <div class="tactical-label">🎯 Rekomendasi Taktis & Tindakan:</div>
            <div class="tactical-action-text">${tac.actionable_recommendation}</div>
          </div>
        ` : ''}
      </div>
    `;
  }

  let equipBtnHtml = '';
  const currentName = data.current_item_name || 'Gear Lama';
  if (currentSlot && data.raw_text) {
    if (isEquip) {
      equipBtnHtml = `
        <button class="btn btn-primary btn-block" id="btn-equip-candidate" style="margin-top: 12px; background: var(--accent-green); color: #000; font-weight: 700; cursor: pointer;">
          🛡️ Pasang ${data.item_name} Sekarang (${data.item_name} LEBIH BAGUS)
        </button>
        <div id="equip-status-msg" style="margin-top: 6px; font-size: 11px; text-align: center; display: none;"></div>
      `;
    } else if (isConditional) {
      equipBtnHtml = `
        <button class="btn btn-primary btn-block" id="btn-equip-candidate" style="margin-top: 12px; background: var(--accent-gold); color: #000; font-weight: 700; cursor: pointer;">
          ⚠️ Pertahankan ${currentName} (Pasang Hanya Jika Butuh Resistensi)
        </button>
        <div id="equip-status-msg" style="margin-top: 6px; font-size: 11px; text-align: center; display: none;"></div>
      `;
    } else if (data.verdict === 'REJECT') {
      equipBtnHtml = `
        <button class="btn btn-block" id="btn-equip-candidate" style="margin-top: 12px; background: rgba(239, 68, 68, 0.15); border: 1px solid var(--accent-red); color: var(--accent-red); font-weight: 600; cursor: pointer; font-size: 11px;">
          🛑 Tahan Gear Lama (${currentName} LEBIH BAGUS — Jangan Pasang ${data.item_name})
        </button>
        <div id="equip-status-msg" style="margin-top: 6px; font-size: 11px; text-align: center; display: none;"></div>
      `;
    }
  }

  const winnerBadgeHtml = (data.verdict === 'REJECT')
    ? `<div style="display: block; background: rgba(239, 68, 68, 0.18); border: 1px solid var(--accent-red); color: #ff9999; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 700; margin-bottom: 8px;">👑 KEPUTUSAN TEGAS: <u>${currentName}</u> LEBIH BAGUS UNTUK BUILD INI</div>`
    : (isEquip ? `<div style="display: block; background: rgba(34, 197, 94, 0.18); border: 1px solid var(--accent-green); color: #86efac; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 700; margin-bottom: 8px;">👑 KEPUTUSAN TEGAS: <u>${data.item_name}</u> LEBIH BAGUS (PASANG SEKARANG)</div>` : '');

  container.innerHTML = `
    <div class="verdict-box ${boxClass}">
      <span class="verdict-badge ${badgeClass}">VERDICT: ${data.verdict}</span>
      <div class="verdict-details">
        ${slotBadgeHtml}
        ${winnerBadgeHtml}
        <div style="font-size: 13px; font-weight: 700; margin-bottom: 4px; color: #FFF;">
          ${data.item_name} (${data.base_type || ''})
        </div>
        <p>${data.reason}</p>
        ${gainsHtml}
        ${tradeOffsHtml}
      </div>
      ${tacticalCardHtml}
      ${data.formatted_report ? `<pre class="report-raw-box">${data.formatted_report}</pre>` : ''}
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

function runClientSideVersusFallback(rawText, container, explicitSlot = null) {
  const targetSlot = explicitSlot || detectSlotFromItemText(rawText, appState.selectedSlot);
  const targetLabel = SLOT_LABELS[targetSlot] || targetSlot.toUpperCase();

  const lines = rawText.split('\n').map(l => l.trim()).filter(Boolean);
  let itemName = "Candidate Item";
  let baseType = "";
  let rarity = "rare";

  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (l.startsWith("Rarity:")) {
      rarity = l.replace("Rarity:", "").trim().toLowerCase();
      if (lines[i + 1] && !lines[i + 1].startsWith("---")) {
        itemName = lines[i + 1];
        if (lines[i + 2] && !lines[i + 2].startsWith("---")) {
          baseType = lines[i + 2];
        }
      }
    }
  }

  const gains = [];
  const lifeMatch = rawText.match(/\+(\d+)\s+to\s+maximum\s+Life/i);
  if (lifeMatch) gains.push(`+${lifeMatch[1]} Life`);
  const fireMatch = rawText.match(/\+(\d+)%\s+to\s+Fire\s+Resistance/i);
  if (fireMatch) gains.push(`+${fireMatch[1]}% Fire Res`);
  const coldMatch = rawText.match(/\+(\d+)%\s+to\s+Cold\s+Resistance/i);
  if (coldMatch) gains.push(`+${coldMatch[1]}% Cold Res`);
  const lightMatch = rawText.match(/\+(\d+)%\s+to\s+Lightning\s+Resistance/i);
  if (lightMatch) gains.push(`+${lightMatch[1]}% Lightning Res`);
  const msMatch = rawText.match(/(\d+)%\s+increased\s+Movement\s+Speed/i);
  if (msMatch) gains.push(`+${msMatch[1]}% Movement Speed`);

  const data = {
    raw_text: rawText,
    item_name: itemName,
    base_type: baseType,
    slot: targetSlot,
    verdict: gains.length > 0 ? "EQUIP_NOW" : "CONDITIONAL_UPGRADE",
    reason: `Evaluasi Heuristik Lokal (Offline / Fallback Mode) — Terdeteksi ${gains.length} peningkatan untuk slot ${targetLabel}.`,
    gains: gains,
    trade_offs: [],
    formatted_report: `[OFFLINE CLIENT EVALUATION]\nItem: ${itemName} (${baseType})\nSlot: ${targetLabel}\nRarity: ${rarity}\n\nPositive Attributes:\n${gains.map(g => '  ' + g).join('\n') || '  None detected'}\n\nInfo: Jalankan server melalui 'uv run python -m companion.cli dashboard' untuk live calculation.`
  };

  recordSlotComparison(targetSlot, rawText, data);
  if (appState.selectedSlot !== targetSlot) {
    selectSlot(targetSlot);
  } else {
    renderCompareForSlot(targetSlot);
  }
}

async function fetchHttpRuntime() {
  try {
    const charId = appState.activeCharId || 'BOMSHAK';
    const res = await fetch(`/api/status?char_id=${encodeURIComponent(charId)}`);
    if (res.ok) {
      const data = await res.json();
      loadDataIntoUI(data.status, data.character, data.objective, data.loadout, data.baseline);
      document.getElementById('last-sync-time').textContent = 'Live Sync: ' + new Date().toLocaleTimeString();
      return;
    }
  } catch (err) {
    console.warn('HTTP API /api/status error, falling back to static files:', err);
  }

  try {
    const [statusRes, objRes] = await Promise.allSettled([
      fetch('/runtime/runtime_status.json').then(r => r.json()),
      fetch('/runtime/CURRENT_OBJECTIVE.json').then(r => r.json())
    ]);

    const statusJson = statusRes.status === 'fulfilled' ? statusRes.value : null;
    const objJson = objRes.status === 'fulfilled' ? objRes.value : null;

    const charId = (statusJson && statusJson.active_character_id) || appState.activeCharId;
    const [charRes, loadoutRes] = await Promise.allSettled([
      fetch(`/runtime/characters/${charId}.json`).then(r => r.json()),
      fetch(`/runtime/loadouts/${charId}.json`).then(r => r.json())
    ]);

    const charJson = charRes.status === 'fulfilled' ? charRes.value : null;
    const loadoutJson = loadoutRes.status === 'fulfilled' ? loadoutRes.value : null;

    loadDataIntoUI(statusJson, charJson, objJson, loadoutJson);
    document.getElementById('last-sync-time').textContent = 'Live Sync: ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.warn('HTTP fetch runtime error:', err);
  }
}

// Setup Tab Navigation
function setupNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      navItems.forEach(i => i.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));

      item.classList.add('active');
      const targetId = item.getAttribute('data-tab');
      const targetTab = document.getElementById(targetId);
      if (targetTab) targetTab.classList.add('active');
    });
  });
}

// Setup File System Access API
function setupFolderAccess() {
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

async function parseUploadedFiles(fileMap) {
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
function setupDragAndDrop() {
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

// Setup Demo Button
function setupDemoButton() {
  const btn = document.getElementById('btn-load-demo');
  if (btn) {
    btn.addEventListener('click', () => {
      if (appState.pollTimer) {
        clearInterval(appState.pollTimer);
        appState.pollTimer = null;
      }
      appState.dirHandle = null;
      loadDataIntoUI(DEMO_DATA.status, DEMO_DATA.character, DEMO_DATA.objective, DEMO_DATA.loadout);
      updateStatusBadge('DEMO MODE (OFFLINE)', 'idle');
    });
  }
}

// Live Polling
function startLivePolling() {
  if (appState.pollTimer) clearInterval(appState.pollTimer);

  updateStatusBadge('CONNECTED: /runtime', 'active');
  readRuntimeFiles();

  // Poll every 2 seconds
  appState.pollTimer = setInterval(readRuntimeFiles, 2000);
}

async function readRuntimeFiles() {
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

function updateStatusBadge(text, stateClass) {
  const label = document.getElementById('status-label');
  const dot = document.getElementById('status-dot');
  if (label) label.textContent = text;
  if (dot) {
    dot.className = `pulse-dot ${stateClass}`;
  }
}

// UI Population
function loadDataIntoUI(status, character, objective, loadout, baseline = null) {
  if (status) {
    appState.runtimeStatus = status;
    const gameTag = document.getElementById('game-status-tag');
    if (gameTag) {
      gameTag.textContent = status.game_process_running
        ? `GAME RUNNING (PID ${status.game_pid || 'ACTIVE'})`
        : 'GAME STOPPED';
      gameTag.style.color = status.game_process_running ? 'var(--accent-green)' : 'var(--text-muted)';
    }
    const heartbeatEl = document.getElementById('stat-heartbeat');
    if (heartbeatEl) {
      heartbeatEl.textContent = status.last_poll
        ? `Active (${new Date(status.last_poll).toLocaleTimeString()})`
        : 'Active (Live)';
    }
  }

  if (character) {
    appState.characterState = character;
    const charLevel = character.level ? (character.level.value || character.level) : 17;
    const charName = character.character_name || character.character_id || 'BOMSHAK';

    const charSelect = document.getElementById('header-char-select');
    if (charSelect && charName && charSelect.value !== charName) {
      charSelect.value = charName;
    }
    const hdrName = document.getElementById('hdr-char-name');
    if (hdrName) hdrName.textContent = charName;
    const hdrClass = document.getElementById('hdr-char-class');
    if (hdrClass) hdrClass.textContent = (character.ascendancy || character.character_class || 'Mercenary').toUpperCase();
    const hdrLevel = document.getElementById('hdr-char-level');
    if (hdrLevel) hdrLevel.textContent = charLevel;
    const hdrZone = document.getElementById('hdr-char-zone');
    if (hdrZone) hdrZone.textContent = `Zone: ${character.current_zone ? (character.current_zone.value || character.current_zone) : 'N/A'}`;

    const loadoutTitle = document.getElementById('equipped-loadout-title');
    if (loadoutTitle) loadoutTitle.textContent = `Equipped Loadout (${charName})`;

    const statLvl = document.getElementById('stat-level');
    if (statLvl) statLvl.textContent = charLevel;
    const statClassSub = document.getElementById('stat-class-sub');
    if (statClassSub) statClassSub.textContent = character.ascendancy || character.character_class;
    const statDeaths = document.getElementById('stat-deaths');
    if (statDeaths) statDeaths.textContent = character.death_count ? (character.death_count.value || character.death_count) : '0';
    const statZone = document.getElementById('stat-zone');
    if (statZone) statZone.textContent = character.current_zone ? (character.current_zone.value || character.current_zone) : 'G2_1';

    const wset = character.equipped_weapon_set ? (character.equipped_weapon_set.value || character.equipped_weapon_set) : 1;
    const statWset = document.getElementById('stat-weapon-set');
    if (statWset) statWset.textContent = `Set ${wset}`;

    if (character.attributes) {
      const s = character.attributes.strength ? (character.attributes.strength.value || character.attributes.strength) : 10;
      const d = character.attributes.dexterity ? (character.attributes.dexterity.value || character.attributes.dexterity) : 14;
      const i = character.attributes.intelligence ? (character.attributes.intelligence.value || character.attributes.intelligence) : 10;

      document.getElementById('val-str').textContent = s;
      document.getElementById('val-dex').textContent = d;
      document.getElementById('val-int').textContent = i;

      document.getElementById('bar-str').style.width = Math.min(100, (s / 50) * 100) + '%';
      document.getElementById('bar-dex').style.width = Math.min(100, (d / 50) * 100) + '%';
      document.getElementById('bar-int').style.width = Math.min(100, (i / 50) * 100) + '%';
    }

    if (character.build_progression) {
      document.getElementById('sb-build-target').textContent = character.build_progression.target_build;
      document.getElementById('sb-build-stage').textContent = `Stage: ${character.build_progression.active_stage}`;
    }

    // Update Level 52 Transition Milestone readiness
    const transPctEl = document.getElementById('transition-pct');
    const reqStatusLvl = document.getElementById('req-status-level');
    const lvlNum = parseInt(charLevel, 10) || 1;
    if (transPctEl) {
      transPctEl.textContent = Math.min(100, Math.round((lvlNum / 52) * 100)) + '%';
    }
    if (reqStatusLvl) {
      reqStatusLvl.textContent = `LVL ${lvlNum} / 52`;
    }
  }

  // Defenses Summary
  let totalArmour = 0;
  let totalEvasion = 0;
  let totalES = 0;
  let totalBonusLife = 0;

  if (baseline) {
    if (baseline.armour && baseline.armour.value != null) totalArmour = baseline.armour.value;
    if (baseline.evasion && baseline.evasion.value != null) totalEvasion = baseline.evasion.value;
    if (baseline.energy_shield && baseline.energy_shield.value != null) totalES = baseline.energy_shield.value;
    if (baseline.life && baseline.life.value != null) totalBonusLife = baseline.life.value;
  } else if (loadout) {
    const allSlots = {
      ...(loadout.shared_slots || {}),
      ...(loadout.weapon_set_1 || {}),
      ...(loadout.weapon_set_2 || {})
    };
    for (const [key, entry] of Object.entries(allSlots)) {
      if (!entry || !entry.item) continue;
      const it = entry.item;
      if (it.local_armour) totalArmour += it.local_armour;
      if (it.local_evasion) totalEvasion += it.local_evasion;
      if (it.local_energy_shield) totalES += it.local_energy_shield;
      if (it.modifiers && Array.isArray(it.modifiers)) {
        for (const m of it.modifiers) {
          if (m.type === 'MAXIMUM_LIFE' && m.magnitude) {
            totalBonusLife += m.magnitude;
          }
        }
      }
    }
  }

  const defArmourEl = document.getElementById('def-armour');
  const defEvasionEl = document.getElementById('def-evasion');
  const defEsEl = document.getElementById('def-es');
  const defLifeEl = document.getElementById('def-life');
  if (defArmourEl) defArmourEl.textContent = totalArmour;
  if (defEvasionEl) defEvasionEl.textContent = totalEvasion;
  if (defEsEl) defEsEl.textContent = totalES;
  if (defLifeEl) defLifeEl.textContent = (totalBonusLife >= 0 ? `+${totalBonusLife}` : `${totalBonusLife}`);

  if (objective) {
    appState.currentObjective = objective;
    const pri = objective.primary_objective;
    if (pri) {
      document.getElementById('primary-obj-title').textContent = pri.title;
      document.getElementById('primary-obj-action').textContent = pri.action;
      document.getElementById('primary-obj-source').textContent = pri.source;
      document.getElementById('primary-obj-rationale').textContent = pri.rationale;
      document.getElementById('primary-obj-horizon').textContent = `Horizon: Next ${pri.horizon || 1} Zone`;
      document.getElementById('primary-obj-risk').textContent = `Risk: ${pri.cost_of_ignoring || 2}`;
      document.getElementById('obj-priority-chip').textContent = `PRIORITY ${pri.priority}`;
    }

    renderObjectivesTable(objective.all_objectives || []);
    document.getElementById('badge-obj-count').textContent = (objective.all_objectives || []).length;
  }

  if (loadout) {
    appState.loadout = loadout;
    renderGearSlots(loadout);
  }
}

function addNotification(title, msg, type = 'info', time = 'Just now') {
  const feed = document.getElementById('notif-feed');
  if (!feed) return;
  const item = document.createElement('div');
  item.className = `notif-item notif-${type}`;
  item.innerHTML = `
    <div class="notif-indicator"></div>
    <div class="notif-content">
      <div class="notif-head">
        <strong class="notif-title">${title}</strong>
        <span class="notif-time">${time}</span>
      </div>
      <p class="notif-msg">${msg}</p>
    </div>
  `;
  feed.insertBefore(item, feed.firstChild);
  while (feed.children.length > 8) {
    feed.removeChild(feed.lastChild);
  }
}

function renderObjectivesTable(objectives) {
  const tbody = document.getElementById('objectives-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  objectives.forEach(obj => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="priority-chip" style="font-size: 9px; padding: 2px 6px;">P${obj.priority}</span></td>
      <td>
        <strong style="color: #FFFFFF; font-size: 13px;">${obj.title}</strong>
        <div style="font-size: 10px; color: var(--text-dim); font-family: var(--font-mono);">${obj.id}</div>
      </td>
      <td style="color: var(--text-gold); font-size: 12px;">${obj.action}</td>
      <td style="font-size: 11px; color: var(--text-muted);">${obj.source}</td>
      <td>
        <span style="font-family: var(--font-mono); font-size: 11px; color: #F59E0B;">Trust: ${obj.evidence_trust || 3}</span>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function selectSlot(slotKey) {
  if (!slotKey) return;
  appState.selectedSlot = slotKey;

  // Update selection in left loadout grid
  document.querySelectorAll('.slot-card').forEach(c => {
    c.classList.toggle('selected', c.dataset.slot === slotKey);
  });

  const label = SLOT_LABELS[slotKey] || slotKey.toUpperCase();
  const slotTitle = document.getElementById('selected-slot-name');
  if (slotTitle) slotTitle.textContent = label.toUpperCase();

  // Find slot data from active loadout
  let slotData = null;
  if (appState.loadout) {
    const sharedSlots = appState.loadout.shared_slots || {};
    const weaponSet1 = appState.loadout.weapon_set_1 || {};
    const weaponSet2 = appState.loadout.weapon_set_2 || {};
    if (slotKey === 'main_hand') slotData = weaponSet1.main_hand || sharedSlots.main_hand;
    else if (slotKey === 'off_hand') slotData = weaponSet1.off_hand || sharedSlots.off_hand;
    else if (slotKey === 'set2_main_hand') slotData = weaponSet2.main_hand;
    else if (slotKey === 'set2_off_hand') slotData = weaponSet2.off_hand;
    else slotData = sharedSlots[slotKey];
  }

  // Update equipped inspector
  renderSlotInspector(label, slotData ? slotData.item : null);

  // Update versus compare panel & history specifically for this slot!
  renderCompareForSlot(slotKey);
}

function renderGearSlots(loadout) {
  const grid = document.getElementById('slots-grid');
  if (!grid) return;
  grid.innerHTML = '';

  const revBadge = document.getElementById('gear-finalized-badge');
  if (revBadge && loadout) {
    revBadge.textContent = `Revision ${loadout.revision || 1} (${loadout.is_finalized ? 'Final' : 'Draft'})`;
  }

  const sharedSlots = loadout.shared_slots || {};
  const weaponSet1 = loadout.weapon_set_1 || {};
  const weaponSet2 = loadout.weapon_set_2 || {};

  // Slot definitions with data resolvers
  const slotDefs = [
    { key: 'helmet', label: 'Helmet', data: sharedSlots.helmet },
    { key: 'body_armour', label: 'Body Armour', data: sharedSlots.body_armour },
    { key: 'gloves', label: 'Gloves', data: sharedSlots.gloves },
    { key: 'boots', label: 'Boots', data: sharedSlots.boots },
    { key: 'amulet', label: 'Amulet', data: sharedSlots.amulet },
    { key: 'ring1', label: 'Ring 1', data: sharedSlots.ring1 },
    { key: 'ring2', label: 'Ring 2', data: sharedSlots.ring2 },
    { key: 'belt', label: 'Belt', data: sharedSlots.belt },
    // Weapon Set 1
    { key: 'main_hand', label: 'Main Hand (Set 1)', data: weaponSet1.main_hand || sharedSlots.main_hand },
    { key: 'off_hand', label: 'Off Hand (Set 1)', data: weaponSet1.off_hand || sharedSlots.off_hand },
    // Weapon Set 2
    { key: 'set2_main_hand', label: 'Main Hand (Set 2)', data: weaponSet2.main_hand },
    { key: 'set2_off_hand', label: 'Off Hand (Set 2)', data: weaponSet2.off_hand }
  ];

  slotDefs.forEach(slotDef => {
    const slotKey = slotDef.key;
    const slotData = slotDef.data;
    const card = document.createElement('div');
    card.dataset.slot = slotKey;
    card.className = `slot-card ${appState.selectedSlot === slotKey ? 'selected' : ''}`;

    const compareInfo = appState.slotCompareData[slotKey];
    let compareBadgeHtml = '';
    if (compareInfo && compareInfo.latestVerdict) {
      if (compareInfo.latestVerdict.verdict === 'EQUIP_NOW') {
        compareBadgeHtml = `<span class="slot-upgrade-badge" title="Rekomendasi upgrade siap dipasang">▲ Upgrade</span>`;
      } else if (compareInfo.latestVerdict.verdict === 'CONDITIONAL_UPGRADE') {
        compareBadgeHtml = `<span class="slot-upgrade-badge" style="background: rgba(234, 179, 8, 0.2); border-color: #EAB308; color: #FACC15;" title="Upgrade kondisional">● Upgrade</span>`;
      }
    }
    const historyCount = compareInfo?.history?.length || 0;
    const historyBadgeHtml = historyCount > 0 ? `<span class="slot-history-tag" title="${historyCount} riwayat evaluasi">📜 ${historyCount}</span>` : '';

    if (slotData && slotData.item) {
      const it = slotData.item;
      card.innerHTML = `
        <div class="slot-header-row">
          <span class="slot-type-label">${slotDef.label}</span>
          <span class="slot-rarity-tag rarity-${it.rarity || 'normal'}">${it.rarity || 'normal'}</span>
        </div>
        <div class="slot-item-name">${it.name || it.base_type}</div>
        <div class="slot-item-base">${it.base_type || ''}</div>
        <div class="slot-card-meta">
          ${compareBadgeHtml}
          ${historyBadgeHtml}
        </div>
      `;
    } else {
      card.innerHTML = `
        <div class="slot-header-row">
          <span class="slot-type-label">${slotDef.label}</span>
          <span class="slot-rarity-tag" style="color: var(--text-dim);">EMPTY / UNKNOWN</span>
        </div>
        <div class="slot-item-name" style="color: var(--text-dim);">Unassigned</div>
        <div class="slot-card-meta">
          ${compareBadgeHtml}
          ${historyBadgeHtml}
        </div>
      `;
    }

    card.addEventListener('click', () => {
      selectSlot(slotKey);
    });

    grid.appendChild(card);
  });

  // Default select first item if none selected
  if (!appState.selectedSlot) {
    selectSlot('helmet');
  } else {
    const selectedEl = grid.querySelector(`[data-slot="${appState.selectedSlot}"]`);
    if (selectedEl) selectedEl.classList.add('selected');
  }
}

function renderSlotInspector(slotKey, item) {
  const container = document.getElementById('item-inspector-content');
  const slotTitle = document.getElementById('selected-slot-name');
  if (slotTitle) slotTitle.textContent = slotKey.toUpperCase();

  if (!item) {
    container.innerHTML = `
      <div class="empty-state">
        <p>Slot <strong>${slotKey}</strong> kosong atau belum diobservasi dalam audit loadout.</p>
      </div>
    `;
    return;
  }

  let modsHtml = '';
  if (item.modifiers && item.modifiers.length > 0) {
    modsHtml = item.modifiers.map(m => `<div class="tt-mod">${m.raw_text}</div>`).join('');
  } else {
    modsHtml = '<div class="tt-mod" style="color: var(--text-dim);">(No explicit modifiers)</div>';
  }

  const advisorText = item.advisor_notes || "Item memenuhi baseline persyaratan build saat ini. Tidak ada konflik mekanik terdeteksi.";

  container.innerHTML = `
    <div class="item-tooltip">
      <div class="tooltip-header">
        <div class="tt-name rarity-${item.rarity || 'normal'}">${item.name}</div>
        <div class="tt-base">${item.base_type}</div>
      </div>
      <div class="tooltip-stats">
        ${item.local_armour ? `<div>Armour: <strong style="color: #fff;">${item.local_armour}</strong></div>` : ''}
        ${item.item_level ? `<div>Item Level: <strong style="color: #fff;">${item.item_level}</strong></div>` : ''}
        ${item.required_level ? `<div>Requires Level: <strong style="color: #fff;">${item.required_level}</strong></div>` : ''}
      </div>
      <div class="tooltip-mods">
        ${modsHtml}
      </div>
    </div>

    <div class="advisor-recommendation-box">
      <div class="adv-title">PoB2 EQUIPMENT ADVISOR RECOMMENDATION</div>
      <div class="adv-body">${advisorText}</div>
    </div>

    <div style="margin-top: 14px;">
      <button class="btn btn-secondary btn-block" id="btn-goto-compare-slot" style="font-size: 11px; padding: 8px; cursor: pointer;">
        ⚡ Ganti / Bandingkan Calon Upgrade untuk Slot Ini (${slotKey.toUpperCase()})
      </button>
    </div>
  `;

  const btnGoto = container.querySelector('#btn-goto-compare-slot');
  if (btnGoto) {
    btnGoto.addEventListener('click', () => {
      const compareTab = document.getElementById('subtab-view-compare');
      if (compareTab) compareTab.click();
      renderCompareForSlot(appState.selectedSlot);
      const textarea = document.getElementById('candidate-textarea');
      if (textarea) textarea.focus();
    });
  }
}

function showTransientNotification(msg) {
  let toast = document.getElementById('dashboard-transient-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'dashboard-transient-toast';
    toast.style.position = 'fixed';
    toast.style.bottom = '24px';
    toast.style.right = '24px';
    toast.style.background = 'rgba(20, 20, 22, 0.95)';
    toast.style.border = '1px solid var(--accent-gold)';
    toast.style.color = '#FFF';
    toast.style.padding = '12px 18px';
    toast.style.borderRadius = '6px';
    toast.style.fontSize = '12px';
    toast.style.fontWeight = '600';
    toast.style.boxShadow = '0 6px 20px rgba(0,0,0,0.6), 0 0 10px rgba(216,169,56,0.2)';
    toast.style.zIndex = '10000';
    toast.style.transition = 'all 0.3s ease';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.display = 'block';
  toast.style.opacity = '1';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => { toast.style.display = 'none'; }, 300);
  }, 3500);
}

function setupSyncModal() {
  const modal = document.getElementById('modal-sync-profile');
  const btnOpen = document.getElementById('btn-open-sync-modal');
  const btnClose = document.getElementById('btn-close-sync-modal');
  if (!modal) return;

  if (btnOpen) {
    btnOpen.addEventListener('click', () => {
      modal.style.display = 'flex';
      const accInput = document.getElementById('sync-account-name');
      if (accInput) accInput.focus();
    });
  }

  if (btnClose) {
    btnClose.addEventListener('click', () => {
      modal.style.display = 'none';
    });
  }

  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.style.display = 'none';
  });

  const tabPublic = document.getElementById('mtab-public-profile');
  const tabJson = document.getElementById('mtab-paste-json');
  const contentPublic = document.getElementById('mcontent-public');
  const contentJson = document.getElementById('mcontent-json');

  if (tabPublic && tabJson && contentPublic && contentJson) {
    tabPublic.addEventListener('click', () => {
      tabPublic.classList.add('active');
      tabJson.classList.remove('active');
      contentPublic.style.display = 'block';
      contentJson.style.display = 'none';
    });
    tabJson.addEventListener('click', () => {
      tabJson.classList.add('active');
      tabPublic.classList.remove('active');
      contentJson.style.display = 'block';
      contentPublic.style.display = 'none';
    });
  }

  const accInput = document.getElementById('sync-account-name');
  const charInput = document.getElementById('sync-character-name');
  const linkBox = document.getElementById('direct-json-link-box');

  function updateDirectLink() {
    const acc = (accInput?.value || '').trim() || 'NAMA_AKUN';
    const ch = (charInput?.value || '').trim() || 'BOMSHAK';
    if (linkBox) {
      linkBox.textContent = `https://www.pathofexile.com/character-window/get-items?accountName=${encodeURIComponent(acc)}&character=${encodeURIComponent(ch)}`;
    }
  }

  if (accInput) accInput.addEventListener('input', updateDirectLink);
  if (charInput) charInput.addEventListener('input', updateDirectLink);

  // Button Do Fetch Public
  const btnFetch = document.getElementById('btn-do-fetch-public');
  const msgPublic = document.getElementById('sync-public-msg');
  if (btnFetch) {
    btnFetch.addEventListener('click', async () => {
      const acc = (accInput?.value || '').trim();
      const ch = (charInput?.value || '').trim() || 'BOMSHAK';
      if (!acc) {
        alert('Harap masukkan nama akun PoE Anda.');
        return;
      }
      btnFetch.disabled = true;
      btnFetch.textContent = '⏳ Menghubungi server GGG...';
      if (msgPublic) {
        msgPublic.style.display = 'block';
        msgPublic.style.color = 'var(--text-muted)';
        msgPublic.textContent = 'Sedang mengambil data karakter dari pathofexile.com...';
      }
      try {
        const chkOverwrite = document.getElementById('sync-public-overwrite');
        const overwrite = chkOverwrite ? chkOverwrite.checked : true;
        const res = await fetch('/api/fetch-public-profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account_name: acc, character_id: ch, overwrite: overwrite })
        });
        const data = await res.json();
        if (data.success) {
          if (msgPublic) {
            msgPublic.style.color = 'var(--accent-green)';
            let details = data.message;
            if (data.warnings && data.warnings.length > 0) {
              details += '<br><span style="font-size: 10px; color: var(--text-dim);">' + data.warnings.join('<br>') + '</span>';
            }
            msgPublic.innerHTML = `✓ ${details}`;
          }
          await fetchHttpRuntime();
          setTimeout(() => { modal.style.display = 'none'; }, 2000);
        } else if (data.url) {
          if (msgPublic) {
            msgPublic.style.color = '#F59E0B';
            msgPublic.innerHTML = `⚠️ ${data.message ? data.message.replace(/\n/g, '<br>') : data.error}<br><br><a href="${data.url}" target="_blank" style="color: #60A5FA; text-decoration: underline; font-weight: bold;">👉 Klik di sini untuk membuka link JSON di browser</a>`;
          }
          const linkBox = document.getElementById('direct-json-link-box');
          if (linkBox && data.url) linkBox.textContent = data.url;
        } else {
          if (msgPublic) {
            msgPublic.style.color = 'var(--accent-red)';
            msgPublic.innerHTML = `✕ ${data.message ? data.message.replace(/\n/g, '<br>') : (data.error || 'Gagal mengambil data')}`;
          }
        }
      } catch (err) {
        if (msgPublic) {
          msgPublic.style.color = 'var(--accent-red)';
          msgPublic.textContent = `✕ Error: ${err.message}`;
        }
      }
      btnFetch.disabled = false;
      btnFetch.textContent = '🔄 Tarik Seluruh Equipment dari GGG';
    });
  }

  // Button Do Import JSON
  const btnImportJson = document.getElementById('btn-do-import-json');
  const textareaJson = document.getElementById('sync-json-textarea');
  const msgJson = document.getElementById('sync-json-msg');
  if (btnImportJson && textareaJson) {
    btnImportJson.addEventListener('click', async () => {
      const rawText = textareaJson.value.trim();
      if (!rawText) {
        alert('Harap paste teks JSON karakter terlebih dahulu.');
        return;
      }
      let parsed = null;
      try {
        parsed = JSON.parse(rawText);
      } catch (err) {
        alert('Format teks yang di-paste bukan JSON valid: ' + err.message);
        return;
      }

      btnImportJson.disabled = true;
      btnImportJson.textContent = '⏳ Menerapkan ke loadout...';
      try {
        const ch = (charInput?.value || '').trim() || 'BOMSHAK';
        const chkOverwrite = document.getElementById('sync-json-overwrite');
        const overwrite = chkOverwrite ? chkOverwrite.checked : true;
        const res = await fetch('/api/import-character', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: ch, character_data: parsed, overwrite: overwrite })
        });
        const resData = await res.json();
        if (resData.success) {
          if (msgJson) {
            msgJson.style.display = 'block';
            msgJson.style.color = 'var(--accent-green)';
            let details = resData.message;
            if (resData.warnings && resData.warnings.length > 0) {
              details += '<br><span style="font-size: 10px; color: var(--text-dim);">' + resData.warnings.join('<br>') + '</span>';
            }
            msgJson.innerHTML = `✓ ${details}`;
          }
          addNotification('Sinkronisasi Karakter', resData.message, 'info');
          await fetchHttpRuntime();
          setTimeout(() => { modal.style.display = 'none'; }, 2000);
        } else {
          if (msgJson) {
            msgJson.style.display = 'block';
            msgJson.style.color = 'var(--accent-red)';
            msgJson.textContent = `✕ ${resData.error || 'Gagal menerapkan JSON'}`;
          }
        }
      } catch (err) {
        if (msgJson) {
          msgJson.style.display = 'block';
          msgJson.style.color = 'var(--accent-red)';
          msgJson.textContent = `✕ Error: ${err.message}`;
        }
      }
      btnImportJson.disabled = false;
      btnImportJson.textContent = '📥 Terapkan Seluruh Equipment ke Loadout';
    });
  }
}

async function setupCharacterAndGuideControls() {
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
          if (guideSelect && !selectedText.toLowerCase().includes('mercenary')) {
            guideSelect.value = 'generic_pob2';
            appState.selectedGuide = 'generic_pob2';
          } else if (guideSelect && selectedText.toLowerCase().includes('mercenary')) {
            guideSelect.value = 'fubgun_flameblast';
            appState.selectedGuide = 'fubgun_flameblast';
          }
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
      const origText = btnSync.textContent;
      btnSync.textContent = '⏳...';
      btnSync.disabled = true;
      try {
        const res = await fetch('/api/fetch-public-profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ character_id: charId, account_name: 'mikaelzo#5674', overwrite: true })
        });
        if (res.ok) {
          const resData = await res.json();
          alert(resData.message || `Berhasil menyinkronkan data untuk ${charId}!`);
          logToTerminal('SYNC', `Sinkronisasi profil selesai untuk ${charId}: ${resData.imported_slots || 0} slot diperbarui`);
          await fetchHttpRuntime();
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

