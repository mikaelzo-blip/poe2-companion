/**
 * PoE2 Hermes Companion Suite - client entry point.
 */
import { setupCompareSubtabs } from './compare.js';
import { setupCharacterAndGuideControls } from './controls.js';
import { setupStatsModal, setupSyncModal } from './modals.js';
import { setupNavigation } from './overview.js';
import { checkHttpHost, setupDragAndDrop, setupFolderAccess } from './runtime.js';

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  setupFolderAccess();
  setupDragAndDrop();
  setupCompareSubtabs();
  setupSyncModal();
  setupStatsModal();
  await setupCharacterAndGuideControls();

  // Try auto-fetching via HTTP if hosted via server
  await checkHttpHost();
});
