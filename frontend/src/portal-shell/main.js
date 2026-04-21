import { createApp } from 'vue';

import App from './App.vue';
import { router } from './router.js';
import '../styles/tailwind.css';
import './style.css';
import { getPendingJobs, deregisterJob } from '../core/pending-jobs-registry.js';
import { restoreUrlState } from '../core/shell-navigation.js';

const PRELOAD_RECOVERY_KEY = 'portal-shell:preload-recovered';
const PRELOAD_RECOVERY_TTL_MS = 2 * 60 * 1000;

function shouldRecoverByReload(storageKey, url, ttlMs) {
  try {
    const raw = window.sessionStorage.getItem(storageKey);
    if (raw) {
      const parsed = JSON.parse(raw);
      const recoveredUrl = String(parsed?.url || '');
      const recoveredAt = Number(parsed?.at || 0);
      if (recoveredUrl === url && Date.now() - recoveredAt < ttlMs) {
        return false;
      }
    }
  } catch {
    // Ignore parse errors and proceed with recovery attempt.
  }

  window.sessionStorage.setItem(
    storageKey,
    JSON.stringify({
      url,
      at: Date.now(),
    }),
  );
  return true;
}

window.addEventListener('vite:preloadError', (event) => {
  event.preventDefault();
  const currentUrl = window.location.href;
  if (!shouldRecoverByReload(PRELOAD_RECOVERY_KEY, currentUrl, PRELOAD_RECOVERY_TTL_MS)) {
    return;
  }
  window.location.reload();
});

const app = createApp(App);
app.use(router);
restoreUrlState();

window.__MES_PORTAL_SHELL_NAVIGATE__ = (target, { replace = false } = {}) => {
  const navigate = replace ? router.replace(target) : router.push(target);
  if (navigate && typeof navigate.catch === 'function') {
    navigate.catch(() => {
      // Avoid uncaught navigation duplicate warnings in browser console.
    });
  }
};

// ---------------------------------------------------------------------------
// Best-effort job abandonment on page unload
//
// When the user navigates away or closes the tab, fire sendBeacon for each
// pending async job so the server can mark them abandoned promptly.
// sendBeacon is used because XHR/fetch are unreliable during unload.
// ---------------------------------------------------------------------------
window.addEventListener('beforeunload', () => {
  const pendingJobs = getPendingJobs();
  for (const { job_id, prefix } of pendingJobs) {
    try {
      const payload = JSON.stringify({ prefix });
      const sent = navigator.sendBeacon(`/api/job/${job_id}/abandon`, new Blob([payload], { type: 'application/json' }));
      if (sent) {
        deregisterJob(job_id);
      }
    } catch {
      // sendBeacon failures must not block unload
    }
  }
});

app.mount('#app');
