import { refreshGuideControls } from './controls.js';
import { appState, esc } from './state.js';

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.json();
}

export async function refreshGuides() {
  const box = document.getElementById('guide-list');
  if (!box) return;
  try {
    const r = await fetch(`/api/guides?char_id=${encodeURIComponent(appState.activeCharId || 'BOMSHAK')}`);
    const { guides = [] } = await r.json();
    box.innerHTML = guides.length
      ? guides.map((g) => `<div style="display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--border-subtle);">
          <span>${esc(g.name)} <span style="color:var(--text-muted)">· ${esc(String(g.stages.length))} stage · PoB: ${g.has_pob ? 'ya' : 'tidak'}</span></span>
          <button class="btn" data-del="${esc(g.slug)}" data-name="${esc(g.name)}">Hapus</button></div>`).join('')
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
      refreshGuides();
      refreshGuideControls();
    } catch (e) {
      show(esc(e.message), 'var(--accent-red, #e55)');
    }
  });

  document.getElementById('guide-list')?.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-del]');
    if (!b || !confirm(`Hapus guide "${b.dataset.name}"?`)) return;
    await post('/api/guides/delete', { slug: b.dataset.del });
    refreshGuides();
    refreshGuideControls();
  });
}
