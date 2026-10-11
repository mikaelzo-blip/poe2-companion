import { refreshGuides, setupGuides } from './guides.js';
import { fetchHttpRuntime } from './runtime.js';
import { addNotification, appState, esc } from './state.js';

export function setupSyncModal() {
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

  const tabs = [['mtab-public-profile', 'mcontent-public'], ['mtab-paste-json', 'mcontent-json'], ['mtab-guides', 'mcontent-guides']]
    .map(([t, c]) => [document.getElementById(t), document.getElementById(c)]);
  for (const [btn] of tabs) {
    btn?.addEventListener('click', () => {
      for (const [b, c] of tabs) {
        b.classList.toggle('active', b === btn);
        c.style.display = b === btn ? 'block' : 'none';
      }
      if (btn.id === 'mtab-guides') refreshGuides();
    });
  }
  setupGuides();

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
            let details = esc(data.message);
            if (data.warnings && data.warnings.length > 0) {
              details += '<br><span style="font-size: 10px; color: var(--text-dim);">' + data.warnings.map(esc).join('<br>') + '</span>';
            }
            msgPublic.innerHTML = `✓ ${details}`;
          }
          await fetchHttpRuntime();
          setTimeout(() => { modal.style.display = 'none'; }, 2000);
        } else if (data.url) {
          if (msgPublic) {
            msgPublic.style.color = '#F59E0B';
            msgPublic.innerHTML = `⚠️ ${data.message ? esc(data.message).replace(/\n/g, '<br>') : esc(data.error)}${/^https:\/\//.test(data.url) ? `<br><br><a href="${esc(data.url)}" target="_blank" rel="noopener" style="color: #60A5FA; text-decoration: underline; font-weight: bold;">👉 Klik di sini untuk membuka link JSON di browser</a>` : ''}`;
          }
          const linkBox = document.getElementById('direct-json-link-box');
          if (linkBox && data.url) linkBox.textContent = data.url;
        } else {
          if (msgPublic) {
            msgPublic.style.color = 'var(--accent-red)';
            msgPublic.innerHTML = `✕ ${data.message ? esc(data.message).replace(/\n/g, '<br>') : esc(data.error || 'Gagal mengambil data')}`;
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
            let details = esc(resData.message);
            if (resData.warnings && resData.warnings.length > 0) {
              details += '<br><span style="font-size: 10px; color: var(--text-dim);">' + resData.warnings.map(esc).join('<br>') + '</span>';
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

export function setupStatsModal() {
  const modal = document.getElementById('modal-sync-stats');
  const btnOpen = document.getElementById('btn-open-stats-modal');
  const btnClose = document.getElementById('btn-close-stats-modal');
  if (!modal) return;

  if (btnOpen) {
    btnOpen.addEventListener('click', () => {
      // Populate fields from current active character / baseline
      const char = appState.runtimeData?.character;
      const base = appState.runtimeData?.baseline;
      const charName = char?.character_name || 'BOMSHAK';
      const charLevel = char?.level ? (char.level.value || char.level) : 37;

      const nameEl = document.getElementById('stat-edit-char-name');
      const lvlEl = document.getElementById('stat-edit-level');
      if (nameEl) nameEl.value = charName;
      if (lvlEl) lvlEl.value = charLevel;

      // Attributes
      const strVal = char?.attributes?.strength ? (char.attributes.strength.value || char.attributes.strength) : 48;
      const dexVal = char?.attributes?.dexterity ? (char.attributes.dexterity.value || char.attributes.dexterity) : 85;
      const intVal = char?.attributes?.intelligence ? (char.attributes.intelligence.value || char.attributes.intelligence) : 53;
      const elStr = document.getElementById('stat-edit-str');
      const elDex = document.getElementById('stat-edit-dex');
      const elInt = document.getElementById('stat-edit-int');
      if (elStr) elStr.value = strVal;
      if (elDex) elDex.value = dexVal;
      if (elInt) elInt.value = intVal;

      // Defenses & Pools
      const lifeVal = base?.life?.value != null ? base.life.value : 723;
      const armVal = base?.armour?.value != null ? base.armour.value : 112;
      const evaVal = base?.evasion?.value != null ? base.evasion.value : 465;
      const esVal = base?.energy_shield?.value != null ? base.energy_shield.value : 47;
      const manaVal = base?.mana?.value != null ? base.mana.value : (char?.resources?.mana?.value ?? 300);
      const spiritVal = base?.spirit?.value != null ? base.spirit.value : (char?.resources?.spirit?.value ?? 30);
      if (document.getElementById('stat-edit-life')) document.getElementById('stat-edit-life').value = lifeVal;
      if (document.getElementById('stat-edit-armour')) document.getElementById('stat-edit-armour').value = armVal;
      if (document.getElementById('stat-edit-evasion')) document.getElementById('stat-edit-evasion').value = evaVal;
      if (document.getElementById('stat-edit-es')) document.getElementById('stat-edit-es').value = esVal;
      if (document.getElementById('stat-edit-mana')) document.getElementById('stat-edit-mana').value = manaVal;
      if (document.getElementById('stat-edit-spirit')) document.getElementById('stat-edit-spirit').value = spiritVal;

      // Resistances
      const fRes = base?.effective_fire_res?.value != null ? base.effective_fire_res.value : (char?.resistances?.fire?.value ?? 23);
      const cRes = base?.effective_cold_res?.value != null ? base.effective_cold_res.value : (char?.resistances?.cold?.value ?? -3);
      const lRes = base?.effective_lightning_res?.value != null ? base.effective_lightning_res.value : (char?.resistances?.lightning?.value ?? -4);
      const chRes = base?.effective_chaos_res?.value != null ? base.effective_chaos_res.value : (char?.resistances?.chaos?.value ?? 0);
      if (document.getElementById('stat-edit-fire')) document.getElementById('stat-edit-fire').value = fRes;
      if (document.getElementById('stat-edit-cold')) document.getElementById('stat-edit-cold').value = cRes;
      if (document.getElementById('stat-edit-light')) document.getElementById('stat-edit-light').value = lRes;
      if (document.getElementById('stat-edit-chaos')) document.getElementById('stat-edit-chaos').value = chRes;

      modal.style.display = 'flex';
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

  const btnSave = document.getElementById('btn-save-character-stats');
  const msgEl = document.getElementById('stat-save-msg');
  if (btnSave) {
    btnSave.addEventListener('click', async () => {
      btnSave.disabled = true;
      btnSave.textContent = '⏳ Menyimpan stat...';
      const charId = document.getElementById('stat-edit-char-name')?.value || 'BOMSHAK';
      const payload = {
        character_id: charId,
        level: parseInt(document.getElementById('stat-edit-level')?.value, 10) || 37,
        strength: parseInt(document.getElementById('stat-edit-str')?.value, 10) || 10,
        dexterity: parseInt(document.getElementById('stat-edit-dex')?.value, 10) || 10,
        intelligence: parseInt(document.getElementById('stat-edit-int')?.value, 10) || 10,
        life: parseInt(document.getElementById('stat-edit-life')?.value, 10) || 723,
        mana: parseInt(document.getElementById('stat-edit-mana')?.value, 10) || 284,
        spirit: parseInt(document.getElementById('stat-edit-spirit')?.value, 10) || 30,
        energy_shield: parseInt(document.getElementById('stat-edit-es')?.value, 10) || 0,
        armour: parseInt(document.getElementById('stat-edit-armour')?.value, 10) || 0,
        evasion: parseInt(document.getElementById('stat-edit-evasion')?.value, 10) || 0,
        fire_res: parseInt(document.getElementById('stat-edit-fire')?.value, 10) || 0,
        cold_res: parseInt(document.getElementById('stat-edit-cold')?.value, 10) || 0,
        lightning_res: parseInt(document.getElementById('stat-edit-light')?.value, 10) || 0,
        chaos_res: parseInt(document.getElementById('stat-edit-chaos')?.value, 10) || 0,
      };

      try {
        const res = await fetch('/api/update-stats', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const resData = await res.json();
        if (resData.success) {
          if (msgEl) {
            msgEl.style.display = 'block';
            msgEl.style.color = 'var(--accent-green)';
            msgEl.textContent = `✓ ${resData.message}`;
          }
          addNotification('Stat Karakter Terupdate', `Level ${payload.level} (${payload.strength} Str, ${payload.dexterity} Dex, ${payload.intelligence} Int)`, 'info');
          await fetchHttpRuntime();
          setTimeout(() => { modal.style.display = 'none'; }, 1500);
        } else {
          if (msgEl) {
            msgEl.style.display = 'block';
            msgEl.style.color = 'var(--accent-red)';
            msgEl.textContent = `✕ ${resData.error || 'Gagal menyimpan stat'}`;
          }
        }
      } catch (err) {
        if (msgEl) {
          msgEl.style.display = 'block';
          msgEl.style.color = 'var(--accent-red)';
          msgEl.textContent = `✕ Error: ${err.message}`;
        }
      }
      btnSave.disabled = false;
      btnSave.textContent = '💾 Simpan & Perbarui Evaluasi Build';
    });
  }
}
