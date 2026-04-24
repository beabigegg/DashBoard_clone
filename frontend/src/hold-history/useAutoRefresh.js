import { onUnmounted, ref } from 'vue';

/**
 * Auto-refresh composable.
 *
 * Schedules repeated calls to fetchFn at intervalMs.
 * Pauses when document is hidden; resumes + fires immediately when visible again.
 * Retains last successful result and exposes a stale indicator on failure.
 */
export function useAutoRefresh({ intervalMs = 60000, fetchFn } = {}) {
  const lastRefreshAt = ref(null);
  const isStale = ref(false);
  const missCount = ref(0);

  let timerId = null;
  let active = false;

  function schedule() {
    if (!active) return;
    timerId = setTimeout(async () => {
      if (!active) return;
      if (document.visibilityState === 'hidden') {
        schedule();
        return;
      }
      await runFetch();
      schedule();
    }, intervalMs);
  }

  async function runFetch() {
    try {
      await fetchFn();
      lastRefreshAt.value = new Date();
      isStale.value = false;
      missCount.value = 0;
    } catch {
      missCount.value += 1;
      if (missCount.value >= 3) {
        isStale.value = true;
      }
    }
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'visible' && active) {
      clearTimeout(timerId);
      timerId = null;
      void runFetch().then(() => {
        if (active) schedule();
      });
    }
  }

  function start() {
    if (active) return;
    active = true;
    isStale.value = false;
    missCount.value = 0;
    document.addEventListener('visibilitychange', onVisibilityChange);
    schedule();
  }

  function stop() {
    active = false;
    clearTimeout(timerId);
    timerId = null;
    document.removeEventListener('visibilitychange', onVisibilityChange);
  }

  onUnmounted(stop);

  return {
    start,
    stop,
    lastRefreshAt,
    isStale,
    missCount,
  };
}
