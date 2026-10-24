import { renderCompareForSlot } from './compare.js';
import { SLOT_LABELS, appState, esc, factVal } from './state.js';

// Setup Tab Navigation
export function setupNavigation() {
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


// UI Population
export function loadDataIntoUI(status, character, objective, loadout, baseline = null) {
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
    const charLevel = factVal(character.level, '?');
    const charName = character.character_name || character.character_id || 'BOMSHAK';

    const charSelect = document.getElementById('header-char-select');
    if (charSelect && charName && charSelect.value !== charName) {
      charSelect.value = charName;
    }
    const hdrName = document.getElementById('hdr-char-name');
    if (hdrName) hdrName.textContent = charName;
    const hdrClass = document.getElementById('hdr-char-class');
    if (hdrClass) hdrClass.textContent = (character.ascendancy || character.character_class || 'Unknown').toUpperCase();
    const hdrLevel = document.getElementById('hdr-char-level');
    if (hdrLevel) hdrLevel.textContent = charLevel;
    const hdrZone = document.getElementById('hdr-char-zone');
    if (hdrZone) hdrZone.textContent = `Zone: ${factVal(character.current_zone, 'N/A')}`;

    const loadoutTitle = document.getElementById('equipped-loadout-title');
    if (loadoutTitle) loadoutTitle.textContent = `Equipped Loadout (${charName})`;

    const statLvl = document.getElementById('stat-level');
    if (statLvl) statLvl.textContent = charLevel;
    const statClassSub = document.getElementById('stat-class-sub');
    if (statClassSub) statClassSub.textContent = character.ascendancy || character.character_class || 'Unknown';
    const statDeaths = document.getElementById('stat-deaths');
    if (statDeaths) statDeaths.textContent = factVal(character.death_count, '-');
    const statZone = document.getElementById('stat-zone');
    if (statZone) statZone.textContent = factVal(character.current_zone, 'N/A');

    const wset = factVal(character.equipped_weapon_set, 1);
    const statWset = document.getElementById('stat-weapon-set');
    if (statWset) statWset.textContent = `Set ${wset}`;

    if (character.attributes) {
      const s = factVal(character.attributes.strength, '-');
      const d = factVal(character.attributes.dexterity, '-');
      const i = factVal(character.attributes.intelligence, '-');

      const elStr = document.getElementById('val-str');
      const elDex = document.getElementById('val-dex');
      const elInt = document.getElementById('val-int');
      if (elStr) elStr.textContent = s;
      if (elDex) elDex.textContent = d;
      if (elInt) elInt.textContent = i;

      const bStr = document.getElementById('bar-str');
      const bDex = document.getElementById('bar-dex');
      const bInt = document.getElementById('bar-int');
      if (bStr) bStr.style.width = Math.min(100, ((Number(s) || 0) / 120) * 100) + '%';
      if (bDex) bDex.style.width = Math.min(100, ((Number(d) || 0) / 120) * 100) + '%';
      if (bInt) bInt.style.width = Math.min(100, ((Number(i) || 0) / 120) * 100) + '%';
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
  const defManaEl = document.getElementById('def-mana');
  if (defArmourEl) defArmourEl.textContent = totalArmour;
  if (defEvasionEl) defEvasionEl.textContent = totalEvasion;
  if (defEsEl) defEsEl.textContent = totalES;
  if (defLifeEl) defLifeEl.textContent = totalBonusLife;
  
  let manaVal = 300;
  let spiritVal = 30;
  if (baseline) {
    if (baseline.mana && baseline.mana.value != null) manaVal = baseline.mana.value;
    if (baseline.spirit && baseline.spirit.value != null) spiritVal = baseline.spirit.value;
  }
  if (character && character.resources) {
    if (character.resources.mana && character.resources.mana.value != null) manaVal = character.resources.mana.value;
    if (character.resources.spirit && character.resources.spirit.value != null) spiritVal = character.resources.spirit.value;
  }
  if (defManaEl) defManaEl.textContent = `${manaVal} / ${spiritVal}`;

  // Resistances Rendering
  let fireRes = 0;
  let coldRes = 0;
  let lightRes = 0;
  let chaosRes = 0;

  if (baseline) {
    if (baseline.effective_fire_res && baseline.effective_fire_res.value != null) fireRes = baseline.effective_fire_res.value;
    else if (baseline.raw_fire_res && baseline.raw_fire_res.value != null) fireRes = baseline.raw_fire_res.value;
    else if (character && character.resistances && character.resistances.fire != null) fireRes = character.resistances.fire.value ?? character.resistances.fire;

    if (baseline.effective_cold_res && baseline.effective_cold_res.value != null) coldRes = baseline.effective_cold_res.value;
    else if (baseline.raw_cold_res && baseline.raw_cold_res.value != null) coldRes = baseline.raw_cold_res.value;
    else if (character && character.resistances && character.resistances.cold != null) coldRes = character.resistances.cold.value ?? character.resistances.cold;

    if (baseline.effective_lightning_res && baseline.effective_lightning_res.value != null) lightRes = baseline.effective_lightning_res.value;
    else if (baseline.raw_lightning_res && baseline.raw_lightning_res.value != null) lightRes = baseline.raw_lightning_res.value;
    else if (character && character.resistances && character.resistances.lightning != null) lightRes = character.resistances.lightning.value ?? character.resistances.lightning;

    if (baseline.effective_chaos_res && baseline.effective_chaos_res.value != null) chaosRes = baseline.effective_chaos_res.value;
    else if (baseline.raw_chaos_res && baseline.raw_chaos_res.value != null) chaosRes = baseline.raw_chaos_res.value;
    else if (character && character.resistances && character.resistances.chaos != null) chaosRes = character.resistances.chaos.value ?? character.resistances.chaos;
  } else if (character && character.resistances) {
    const r = character.resistances;
    if (r.fire) fireRes = r.fire.value != null ? r.fire.value : r.fire;
    if (r.cold) coldRes = r.cold.value != null ? r.cold.value : r.cold;
    if (r.lightning) lightRes = r.lightning.value != null ? r.lightning.value : r.lightning;
    if (r.chaos) chaosRes = r.chaos.value != null ? r.chaos.value : r.chaos;
  }

  const setResBadge = (valElId, boxElId, val) => {
    const valEl = document.getElementById(valElId);
    const boxEl = document.getElementById(boxElId);
    if (!valEl) return;
    valEl.textContent = `${val}%`;
    if (val < 0) {
      valEl.style.color = '#ef4444';
      valEl.style.fontWeight = '800';
      if (boxEl) {
        boxEl.style.background = 'rgba(239, 68, 68, 0.15)';
        boxEl.style.border = '1px solid rgba(239, 68, 68, 0.5)';
      }
    } else if (val >= 75) {
      valEl.style.color = '#4ade80';
      valEl.style.fontWeight = '700';
      if (boxEl) {
        boxEl.style.background = 'rgba(74, 222, 128, 0.1)';
        boxEl.style.border = '1px solid rgba(74, 222, 128, 0.4)';
      }
    } else {
      valEl.style.color = '#ffaa88';
      valEl.style.fontWeight = '600';
      if (boxEl) {
        boxEl.style.background = 'rgba(255, 100, 50, 0.08)';
        boxEl.style.border = '1px solid rgba(255, 100, 50, 0.25)';
      }
    }
  };

  setResBadge('val-fire-res', 'res-box-fire', fireRes);
  setResBadge('val-cold-res', 'res-box-cold', coldRes);
  setResBadge('val-light-res', 'res-box-light', lightRes);
  setResBadge('val-chaos-res', 'res-box-chaos', chaosRes);

  const resCaptionEl = document.getElementById('res-status-caption');
  if (resCaptionEl) {
    const negs = [];
    if (fireRes < 0) negs.push(`Fire ${fireRes}%`);
    if (coldRes < 0) negs.push(`Cold ${coldRes}%`);
    if (lightRes < 0) negs.push(`Lightning ${lightRes}%`);
    if (negs.length > 0) {
      resCaptionEl.textContent = `⚠️ Negatif: ${negs.join(', ')} Rawan One-Shot!`;
      resCaptionEl.style.color = '#ef4444';
      resCaptionEl.style.fontWeight = '700';
    } else {
      const uncapped = [];
      if (fireRes < 75) uncapped.push(`Fire ${fireRes}%`);
      if (coldRes < 75) uncapped.push(`Cold ${coldRes}%`);
      if (lightRes < 75) uncapped.push(`Lightning ${lightRes}%`);
      if (uncapped.length > 0) {
        resCaptionEl.textContent = `Target 75%: ${uncapped.join(', ')}`;
        resCaptionEl.style.color = '#facc15';
        resCaptionEl.style.fontWeight = '600';
      } else {
        resCaptionEl.textContent = '✅ Capped 75%!';
        resCaptionEl.style.color = '#4ade80';
        resCaptionEl.style.fontWeight = '700';
      }
    }
  }

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

export function renderObjectivesTable(objectives) {
  const tbody = document.getElementById('objectives-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  objectives.forEach(obj => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="priority-chip" style="font-size: 9px; padding: 2px 6px;">P${esc(obj.priority)}</span></td>
      <td>
        <strong style="color: #FFFFFF; font-size: 13px;">${esc(obj.title)}</strong>
        <div style="font-size: 10px; color: var(--text-dim); font-family: var(--font-mono);">${esc(obj.id)}</div>
      </td>
      <td class="obj-action" style="color: var(--text-gold); font-size: 12px;">${esc(obj.action)}${obj.id === 'guide:regex' ? ' <button class="btn-copy-regex" type="button">Salin</button>' : ''}</td>
      <td style="font-size: 11px; color: var(--text-muted);">${esc(obj.source)}</td>
      <td>
        <span style="font-family: var(--font-mono); font-size: 11px; color: #F59E0B;">Trust: ${esc(obj.evidence_trust || 3)}</span>
      </td>
    `;
    const copyBtn = tr.querySelector('.btn-copy-regex');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(obj.action).then(
          () => { copyBtn.textContent = 'Tersalin'; },
          () => { copyBtn.textContent = 'Gagal'; },
        );
      });
    }
    tbody.appendChild(tr);
  });
}

export function selectSlot(slotKey) {
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

export function renderGearSlots(loadout) {
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
          <span class="slot-rarity-tag rarity-${esc(it.rarity || 'normal')}">${esc(it.rarity || 'normal')}</span>
        </div>
        <div class="slot-item-name">${esc(it.name || it.base_type)}</div>
        <div class="slot-item-base">${esc(it.base_type || '')}</div>
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

export function renderSlotInspector(slotKey, item) {
  const container = document.getElementById('item-inspector-content');
  const slotTitle = document.getElementById('selected-slot-name');
  if (slotTitle) slotTitle.textContent = slotKey.toUpperCase();

  if (!item) {
    container.innerHTML = `
      <div class="empty-state">
        <p>Slot <strong>${esc(slotKey)}</strong> kosong atau belum diobservasi dalam audit loadout.</p>
      </div>
    `;
    return;
  }

  let modsHtml = '';
  if (item.modifiers && item.modifiers.length > 0) {
    modsHtml = item.modifiers.map(m => `<div class="tt-mod">${esc(m.raw_text)}</div>`).join('');
  } else {
    modsHtml = '<div class="tt-mod" style="color: var(--text-dim);">(No explicit modifiers)</div>';
  }

  const advisorText = item.advisor_notes || "Item memenuhi baseline persyaratan build saat ini. Tidak ada konflik mekanik terdeteksi.";

  container.innerHTML = `
    <div class="item-tooltip">
      <div class="tooltip-header">
        <div class="tt-name rarity-${esc(item.rarity || 'normal')}">${esc(item.name)}</div>
        <div class="tt-base">${esc(item.base_type)}</div>
      </div>
      <div class="tooltip-stats">
        ${item.local_armour ? `<div>Armour: <strong style="color: #fff;">${esc(item.local_armour)}</strong></div>` : ''}
        ${item.item_level ? `<div>Item Level: <strong style="color: #fff;">${esc(item.item_level)}</strong></div>` : ''}
        ${item.required_level ? `<div>Requires Level: <strong style="color: #fff;">${esc(item.required_level)}</strong></div>` : ''}
      </div>
      <div class="tooltip-mods">
        ${modsHtml}
      </div>
    </div>

    <div class="advisor-recommendation-box">
      <div class="adv-title">PoB2 EQUIPMENT ADVISOR RECOMMENDATION</div>
      <div class="adv-body">${esc(advisorText)}</div>
    </div>

    <div style="margin-top: 14px;">
      <button class="btn btn-secondary btn-block" id="btn-goto-compare-slot" style="font-size: 11px; padding: 8px; cursor: pointer;">
        ⚡ Ganti / Bandingkan Calon Upgrade untuk Slot Ini (${esc(slotKey.toUpperCase())})
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


const pct = (v) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;

export function setupSlotRanking() {
  const btn = document.getElementById('btn-slot-ranking');
  const out = document.getElementById('slot-ranking-result');
  if (!btn || !out) return;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    out.innerHTML = '<p style="font-size: 12px;">Menghitung di PoB2 (bisa 10-60 detik)…</p>';
    try {
      const res = await fetch('/api/slot-ranking', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ character_id: appState.activeCharId }),
      });
      const data = await res.json();
      if (!data.success) {
        out.innerHTML = `<p style="color: #EF4444; font-size: 12px;">${esc(data.error || 'Gagal menghitung ranking.')}</p>`;
        return;
      }
      const rows = data.rows.map((r, i) => `
        <tr>
          <td>${i + 1}</td>
          <td><strong>${esc(r.slot)}</strong></td>
          <td>${esc(r.current_item || '-')}</td>
          <td>${esc(r.guide_item)}</td>
          <td style="color: ${r.dps_pct >= 0 ? '#10B981' : '#EF4444'};">${pct(r.dps_pct)}</td>
          <td style="color: ${r.ehp_pct >= 0 ? '#10B981' : '#EF4444'};">${pct(r.ehp_pct)}</td>
        </tr>`).join('');
      const skipped = (data.skipped || []).map((s) => `<li>${esc(s)}</li>`).join('');
      out.innerHTML = `
        <p style="font-size: 11px; color: var(--text-muted);">Stage: ${esc(data.stage)} · Skill: ${esc(data.main_skill || '-')}</p>
        <table class="data-table">
          <thead><tr><th>#</th><th>Slot</th><th>Sekarang</th><th>Target guide</th><th>DPS</th><th>EHP</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        ${skipped ? `<ul style="font-size: 11px; color: var(--text-muted);">${skipped}</ul>` : ''}`;
    } catch (e) {
      out.innerHTML = `<p style="color: #EF4444; font-size: 12px;">${esc(String(e))}</p>`;
    } finally {
      btn.disabled = false;
    }
  });
}
