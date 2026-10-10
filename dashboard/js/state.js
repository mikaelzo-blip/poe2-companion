// Global State
export const appState = {
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

export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

export const SLOT_LABELS = {
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

export function getEffectiveStage() {
  // Server infers the stage when "auto".
  return appState.selectedStage || 'auto';
}

export let logEventCount = 0;

export function logToTerminal(category, message) {
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

export function updateStatusBadge(text, stateClass) {
  const label = document.getElementById('status-label');
  const dot = document.getElementById('status-dot');
  if (label) label.textContent = text;
  if (dot) {
    dot.className = `pulse-dot ${stateClass}`;
  }
}


export function addNotification(title, msg, type = 'info', time = 'Just now') {
  const feed = document.getElementById('notif-feed');
  if (!feed) return;
  const item = document.createElement('div');
  item.className = `notif-item notif-${type}`;
  item.innerHTML = `
    <div class="notif-indicator"></div>
    <div class="notif-content">
      <div class="notif-head">
        <strong class="notif-title">${esc(title)}</strong>
        <span class="notif-time">${esc(time)}</span>
      </div>
      <p class="notif-msg">${esc(msg)}</p>
    </div>
  `;
  feed.insertBefore(item, feed.firstChild);
  while (feed.children.length > 8) {
    feed.removeChild(feed.lastChild);
  }
}

export function showTransientNotification(msg) {
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
