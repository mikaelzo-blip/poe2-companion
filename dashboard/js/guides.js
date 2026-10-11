import { refreshGuideControls } from './controls.js';
import { appState, esc } from './state.js';

let cachedGuides = [];

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.json();
}

function renderRuleItems(rules, slug) {
  if (!rules || !rules.length) {
    return '<div style="font-size:11px;color:var(--text-muted);font-style:italic;padding:4px 0;">Belum ada aturan breaker.</div>';
  }
  return rules.map((r, idx) => {
    const exc = Array.isArray(r.exclude_slots) ? r.exclude_slots.join(', ') : String(r.exclude_slots || '');
    return `
      <div class="rule-row" style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.06);">
        <div style="font-size:11px;line-height:1.4;">
          <div style="color:#fff;font-weight:600;">${esc(r.reason)}</div>
          <div style="color:var(--text-muted);font-family:var(--font-mono);font-size:10px;">Pola: <code>${esc(r.pattern)}</code></div>
          <div style="color:var(--text-muted);font-size:10px;">
            Level: ${esc(String(r.from_level ?? 1))} · Exclude: ${esc(exc || '-')}
          </div>
        </div>
        <button type="button" class="btn btn-del-rule" data-slug="${esc(slug)}" data-rule-idx="${idx}" style="font-size:10px;padding:2px 8px;">Hapus</button>
      </div>
    `;
  }).join('');
}

function renderGuideRow(g) {
  const ruleCount = (g.editingRules || []).length;
  const reimportLink = g.source_url
    ? `<a href="${esc(g.source_url)}" target="_blank" rel="noopener" class="btn" style="font-size:11px;color:var(--accent-gold);border:1px solid var(--accent-gold);text-decoration:none;padding:2px 8px;border-radius:4px;">Buka halaman guide</a>`
    : '';

  return `
    <div class="guide-item" data-slug="${esc(g.slug)}" style="padding:8px 0;border-bottom:1px solid var(--border-subtle);">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
        <span>
          <strong>${esc(g.name)}</strong>
          <span style="color:var(--text-muted);font-size:11px;"> · ${esc(String((g.stages || []).length))} stage · PoB: ${g.has_pob ? 'ya' : 'tidak'}</span>
        </span>
        <div style="display:flex;gap:6px;align-items:center;">
          ${reimportLink}
          <button type="button" class="btn btn-rules-toggle" data-toggle-rules="${esc(g.slug)}">Aturan (${ruleCount})</button>
          <button type="button" class="btn" data-del="${esc(g.slug)}" data-name="${esc(g.name)}">Hapus</button>
        </div>
      </div>

      <div class="rules-editor" id="rules-editor-${esc(g.slug)}" style="display:none;margin-top:10px;padding:10px;background:rgba(0,0,0,0.3);border:1px solid var(--border-subtle);border-radius:4px;">
        <div class="rules-list-container" id="rules-list-${esc(g.slug)}">
          ${renderRuleItems(g.editingRules || [], g.slug)}
        </div>

        <div class="rule-add-form" style="margin-top:10px;padding-top:10px;border-top:1px dashed var(--border-subtle);">
          <div style="font-size:11px;font-weight:bold;margin-bottom:6px;color:var(--accent-gold);">Tambah Aturan Breaker</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px;">
            <div>
              <label style="display:block;font-size:10px;color:var(--text-muted);margin-bottom:2px;">Pattern (regex)</label>
              <input type="text" class="rule-input-pattern" placeholder="e.g. adds .*fire damage" style="width:100%;box-sizing:border-box;font-size:11px;padding:4px;background:#1a1a1a;border:1px solid var(--border-subtle);color:#fff;border-radius:3px;">
            </div>
            <div>
              <label style="display:block;font-size:10px;color:var(--text-muted);margin-bottom:2px;">From Level</label>
              <input type="number" class="rule-input-from-level" value="1" min="1" max="100" style="width:100%;box-sizing:border-box;font-size:11px;padding:4px;background:#1a1a1a;border:1px solid var(--border-subtle);color:#fff;border-radius:3px;">
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;">
            <div>
              <label style="display:block;font-size:10px;color:var(--text-muted);margin-bottom:2px;">Exclude Slots (koma)</label>
              <input type="text" class="rule-input-exclude-slots" placeholder="e.g. Weapon 1, Weapon 2" style="width:100%;box-sizing:border-box;font-size:11px;padding:4px;background:#1a1a1a;border:1px solid var(--border-subtle);color:#fff;border-radius:3px;">
            </div>
            <div>
              <label style="display:block;font-size:10px;color:var(--text-muted);margin-bottom:2px;">Reason</label>
              <input type="text" class="rule-input-reason" placeholder="Alasan aturan..." style="width:100%;box-sizing:border-box;font-size:11px;padding:4px;background:#1a1a1a;border:1px solid var(--border-subtle);color:#fff;border-radius:3px;">
            </div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">
            <button type="button" class="btn btn-save-rules" data-save-rules="${esc(g.slug)}" style="background:var(--accent-gold);color:#000;font-weight:bold;font-size:11px;padding:4px 10px;">Simpan aturan</button>
          </div>
          <div class="rule-error-msg" id="rule-error-${esc(g.slug)}" style="display:none;color:var(--accent-red,#e55);font-size:11px;margin-top:6px;"></div>
        </div>

        <div style="font-size:11px;color:var(--text-muted);margin-top:8px;font-style:italic;">
          Impor ulang guide Fubgun tanpa aturan akan memasang aturan bawaan lagi.
        </div>
      </div>
    </div>
  `;
}

function updateRulesView(g) {
  const listContainer = document.getElementById(`rules-list-${g.slug}`);
  if (listContainer) {
    listContainer.innerHTML = renderRuleItems(g.editingRules || [], g.slug);
  }
  const toggleBtn = document.querySelector(`[data-toggle-rules="${g.slug}"]`);
  if (toggleBtn) {
    toggleBtn.textContent = `Aturan (${(g.editingRules || []).length})`;
  }
}

export async function refreshGuides() {
  const box = document.getElementById('guide-list');
  if (!box) return;
  try {
    const r = await fetch(`/api/guides?char_id=${encodeURIComponent(appState.activeCharId || 'BOMSHAK')}`);
    const { guides = [] } = await r.json();
    cachedGuides = guides.map((g) => ({
      ...g,
      breaker_rules: g.breaker_rules || [],
      editingRules: (g.breaker_rules || []).map((rule) => ({
        pattern: rule.pattern || '',
        from_level: rule.from_level ?? 1,
        exclude_slots: Array.isArray(rule.exclude_slots) ? [...rule.exclude_slots] : [],
        reason: rule.reason || '',
      })),
    }));
    box.innerHTML = cachedGuides.length
      ? cachedGuides.map(renderGuideRow).join('')
      : '<span style="color:var(--text-muted)">Belum ada guide.</span>';
  } catch (e) {
    box.textContent = `Gagal memuat daftar guide: ${e.message}`;
  }
}

export function setupGuides() {
  const msg = document.getElementById('guide-import-msg');
  const show = (html, color) => {
    msg.style.display = 'block';
    msg.style.color = color;
    msg.innerHTML = html;
  };

  // Bookmarklet href = "javascript:" + encoded source of /bookmarklet.js
  fetch('/bookmarklet.js')
    .then((r) => r.text())
    .then((t) => { document.getElementById('guide-bookmarklet').href = 'javascript:' + encodeURIComponent(t); })
    .catch(() => {});

  document.getElementById('btn-do-import-guide')?.addEventListener('click', async () => {
    const ta = document.getElementById('guide-import-textarea');
    try {
      const res = await post('/api/guides', { text: ta.value });
      if (res.error) return show(esc(res.error), 'var(--accent-red, #e55)');
      const warns = (res.warnings || []).map((w) => `<br>⚠ ${esc(w)}`).join('');
      show(`✅ ${esc(res.name)}: ${esc(String(res.stages))} stage diimpor.${warns}`, 'var(--accent-green)');
      ta.value = '';
      await refreshGuides();
      await refreshGuideControls();
    } catch (e) {
      show(esc(e.message), 'var(--accent-red, #e55)');
    }
  });

  document.getElementById('guide-list')?.addEventListener('click', async (e) => {
    // Delete guide
    const bDel = e.target.closest('[data-del]');
    if (bDel) {
      if (!confirm(`Hapus guide "${bDel.dataset.name}"?`)) return;
      await post('/api/guides/delete', { slug: bDel.dataset.del });
      await refreshGuides();
      await refreshGuideControls();
      return;
    }

    // Toggle rules editor
    const bToggle = e.target.closest('[data-toggle-rules]');
    if (bToggle) {
      const slug = bToggle.dataset.toggleRules;
      const editor = document.getElementById(`rules-editor-${slug}`);
      if (editor) {
        editor.style.display = editor.style.display === 'none' ? 'block' : 'none';
      }
      return;
    }

    // Delete single rule from list
    const bDelRule = e.target.closest('.btn-del-rule');
    if (bDelRule) {
      const slug = bDelRule.dataset.slug;
      const idx = parseInt(bDelRule.dataset.ruleIdx, 10);
      const g = cachedGuides.find((guide) => guide.slug === slug);
      if (g && !isNaN(idx)) {
        g.editingRules.splice(idx, 1);
        updateRulesView(g);
      }
      return;
    }

    // Save rules
    const bSave = e.target.closest('[data-save-rules]');
    if (bSave) {
      const slug = bSave.dataset.saveRules;
      const g = cachedGuides.find((guide) => guide.slug === slug);
      if (!g) return;
      const editor = document.getElementById(`rules-editor-${slug}`);
      const patInput = editor?.querySelector('.rule-input-pattern');
      const lvlInput = editor?.querySelector('.rule-input-from-level');
      const excInput = editor?.querySelector('.rule-input-exclude-slots');
      const rsnInput = editor?.querySelector('.rule-input-reason');
      const errBox = document.getElementById(`rule-error-${slug}`);

      const newPattern = (patInput?.value || '').trim();
      const rulesToPost = (g.editingRules || []).map((r) => ({
        pattern: r.pattern,
        from_level: r.from_level,
        exclude_slots: [...(r.exclude_slots || [])],
        reason: r.reason,
      }));

      if (newPattern) {
        const newLvl = parseInt(lvlInput?.value, 10);
        const newExc = (excInput?.value || '')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean);
        const newRsn = (rsnInput?.value || '').trim();
        rulesToPost.push({
          pattern: newPattern,
          from_level: isNaN(newLvl) ? 1 : newLvl,
          exclude_slots: newExc,
          reason: newRsn,
        });
      }

      try {
        const res = await post('/api/guides/rules', {
          slug: g.slug,
          rules: rulesToPost,
        });
        if (res.error) {
          if (errBox) {
            errBox.textContent = res.error;
            errBox.style.display = 'block';
          }
          // Revert editingRules to committed breaker_rules so rendered list still has original rules
          g.editingRules = (g.breaker_rules || []).map((rule) => ({
            pattern: rule.pattern || '',
            from_level: rule.from_level ?? 1,
            exclude_slots: Array.isArray(rule.exclude_slots) ? [...rule.exclude_slots] : [],
            reason: rule.reason || '',
          }));
          updateRulesView(g);
          return;
        }

        if (errBox) {
          errBox.textContent = '';
          errBox.style.display = 'none';
        }
        if (patInput) patInput.value = '';
        if (lvlInput) lvlInput.value = '1';
        if (excInput) excInput.value = '';
        if (rsnInput) rsnInput.value = '';

        g.breaker_rules = rulesToPost;
        g.editingRules = rulesToPost.map((rule) => ({
          pattern: rule.pattern || '',
          from_level: rule.from_level ?? 1,
          exclude_slots: Array.isArray(rule.exclude_slots) ? [...rule.exclude_slots] : [],
          reason: rule.reason || '',
        }));
        updateRulesView(g);
      } catch (err) {
        if (errBox) {
          errBox.textContent = err.message || 'Gagal menyimpan aturan';
          errBox.style.display = 'block';
        }
      }
    }
  });
}
