/**
 * Build Tracker tab: per-act checklist from the active character's guide.
 * Gear rows are computed by the server; gem steps, quest rewards and notables are ticked by hand.
 */
import { appState, esc } from './state.js';

const KIND_LABEL = { KEY_STONE: 'Keystone', ASCENDANCY_LARGE: 'Ascendancy', ASCENDANCY: 'Ascendancy' };

function matchColor(pct) {
  if (pct === null || pct === undefined) return 'var(--text-muted)';
  return pct >= 100 ? 'var(--accent-green)' : pct >= 50 ? 'var(--accent-gold)' : '#EF4444';
}

function checkItem(it, label, detail = '') {
  return `
    <label class="tracker-item${it.done ? ' done' : ''}">
      <input type="checkbox" data-tick="${esc(it.id)}"${it.done ? ' checked' : ''}>
      <span>${label}${detail ? `<small>${detail}</small>` : ''}</span>
    </label>`;
}

function renderGear(rows) {
  if (!rows.length) return '';
  const body = rows.map((r) => `
    <tr>
      <td><strong>${esc(r.slot)}</strong></td>
      <td>${esc(r.guide_item)} <span class="tracker-muted">(${esc(r.is_unique ? 'Unique' : r.item_class)})</span></td>
      <td class="tracker-match" style="color:${matchColor(r.match_pct)};">${r.match_pct === null ? '-' : `${r.match_pct}%`}</td>
      <td>${r.missing.length ? r.missing.map(esc).join('<br>') : (r.done ? '✓' : '')}</td>
    </tr>`).join('');
  return `
    <div class="tracker-block">
      <h3>Gear vs guide</h3>
      <div class="objectives-table-wrap">
        <table class="data-table">
          <thead><tr><th>Slot</th><th>Target guide</th><th>Cocok</th><th>Mod kurang</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      <p class="tracker-muted">Dihitung dari item yang terpasang; unique cocok bila namanya sama.</p>
    </div>`;
}

function renderSection(sec) {
  const gems = sec.items.filter((i) => i.kind === 'gem');
  const quests = sec.items.filter((i) => i.kind === 'quest');
  const done = sec.items.filter((i) => i.done).length;
  const list = [
    gems.length ? '<h4>Gem</h4>' + gems.map((g) => checkItem(g, esc(g.text))).join('') : '',
    quests.length ? '<h4>Quest reward</h4>' + quests.map((q) =>
      checkItem(q, `${esc(q.text)} — ${esc(q.detail)}`, esc(q.group))).join('') : '',
  ].join('');
  return `
    <details class="tracker-act${sec.current ? ' current' : ''}"${sec.current ? ' open' : ''}>
      <summary><span>${esc(sec.key)}${sec.current ? ' <span class="tracker-kind">SEKARANG</span>' : ''}</span>
        <span class="tracker-match" data-count="${esc(sec.key)}">${done}/${sec.items.length}</span></summary>
      <div class="tracker-list">${list}</div>
    </details>`;
}

function renderPassives(passives) {
  const nodes = passives.filter((p) => p.kind === 'node');
  const hints = passives.filter((p) => p.kind === 'hint');
  if (!nodes.length && !hints.length) return '';
  return `
    <div class="tracker-block">
      <h3>Passive tree</h3>
      ${nodes.length ? '<h4 class="tracker-muted">Urutan notable (guide)</h4>' : ''}
      ${nodes.map((n, i) => checkItem(n, `${i + 1}. ${esc(n.text)}${KIND_LABEL[n.group] ? `<span class="tracker-kind">${KIND_LABEL[n.group]}</span>` : ''}`)).join('')}
      ${hints.length ? `<ul class="tracker-muted">${hints.map((h) => `<li>${esc(h.text)}</li>`).join('')}</ul>` : ''}
    </div>`;
}

function updateProgress(data) {
  const el = document.getElementById('tracker-progress');
  if (el && data.progress) el.textContent = `${data.progress.done}/${data.progress.total} selesai`;
}

let current = null;

/** Reload only when the tab is showing (character switches call this). */
export function refreshTrackerIfVisible() {
  if (document.getElementById('tab-tracker')?.classList.contains('active')) loadTracker();
}

export async function loadTracker() {
  const body = document.getElementById('tracker-body');
  if (!body) return;
  try {
    const r = await fetch(`/api/tracker?char_id=${encodeURIComponent(appState.activeCharId || '')}`);
    const data = await r.json();
    if (!data.success) {
      current = null;
      document.getElementById('tracker-progress').textContent = '';
      body.innerHTML = `<p class="tracker-muted">${esc(data.error || 'Tracker tidak tersedia.')}</p>`;
      return;
    }
    current = data;
    const src = data.source_url ? ` · <a href="${esc(data.source_url)}" target="_blank" rel="noopener">sumber</a>` : '';
    body.innerHTML = `
      <p class="tracker-meta">${esc(data.character_id)} · Lvl ${esc(data.character_level ?? '?')} · ${esc(data.act)}
        · ${esc(data.guide)} (${esc(data.stage)})${src}</p>
      ${renderGear(data.gear)}
      <div class="tracker-block"><h3>Checklist per act</h3>${data.sections.map(renderSection).join('')}</div>
      ${renderPassives(data.passives)}`;
    updateProgress(data);
  } catch (e) {
    body.innerHTML = `<p style="color:#EF4444;font-size:12px;">${esc(String(e))}</p>`;
  }
}

async function onTick(box) {
  const id = box.dataset.tick;
  const done = box.checked;
  box.disabled = true;
  try {
    const r = await fetch('/api/tracker/tick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_id: current.character_id, id, done }),
    });
    const res = await r.json();
    if (!res.success) throw new Error(res.error || 'Gagal menyimpan');
    box.closest('.tracker-item').classList.toggle('done', done);
    const all = [...current.sections.flatMap((s) => s.items), ...current.passives];
    all.filter((i) => i.id === id).forEach((i) => { i.done = done; });
    current.progress.done += done ? 1 : -1;
    updateProgress(current);
    current.sections.forEach((s) => {
      const c = document.querySelector(`[data-count="${CSS.escape(s.key)}"]`);
      if (c) c.textContent = `${s.items.filter((i) => i.done).length}/${s.items.length}`;
    });
  } catch (e) {
    box.checked = !done;
    alert(e.message);
  } finally {
    box.disabled = false;
  }
}

export function setupTracker() {
  document.querySelector('.nav-item[data-tab="tab-tracker"]')?.addEventListener('click', loadTracker);
  document.getElementById('tracker-body')?.addEventListener('change', (ev) => {
    if (ev.target.matches('input[data-tick]') && current) onTick(ev.target);
  });
}
