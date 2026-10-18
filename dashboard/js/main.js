/**
 * PoE2 Hermes Companion Suite - client entry point.
 */
import { setupCompareSubtabs } from './compare.js';
import { setupCharacterAndGuideControls } from './controls.js';
import { setupStatsModal, setupSyncModal } from './modals.js';
import { setupNavigation, setupSlotRanking } from './overview.js';
import { checkHttpHost, setupDragAndDrop, setupFolderAccess } from './runtime.js';
import { setupTracker } from './tracker.js';

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupSlotRanking();
  setupFolderAccess();
  setupDragAndDrop();
  setupCompareSubtabs();
  setupSyncModal();
  setupStatsModal();
  setupTracker();
  await setupCharacterAndGuideControls();

  // Try auto-fetching via HTTP if hosted via server
  await checkHttpHost();
});
