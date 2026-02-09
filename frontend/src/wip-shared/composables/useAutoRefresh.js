import { onBeforeUnmount, onMounted } from 'vue';

const DEFAULT_REFRESH_INTERVAL_MS = 10 * 60 * 1000;

export function useAutoRefresh({
  onRefresh,
  intervalMs = DEFAULT_REFRESH_INTERVAL_MS,
  autoStart = true,
  refreshOnVisible = true,
} = {}) {
  let refreshTimer = null;
  const controllers = new Map();

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(() => {
      if (!document.hidden) {
        void onRefresh?.();
      }
    }, intervalMs);
  }

  function resetAutoRefresh() {
    startAutoRefresh();
  }

  function createAbortSignal(key = 'default') {
    const previous = controllers.get(key);
    if (previous) {
      previous.abort();
    }

    const controller = new AbortController();
    controllers.set(key, controller);
    return controller.signal;
  }

  function clearAbortController(key = 'default') {
    const controller = controllers.get(key);
    if (controller) {
      controller.abort();
      controllers.delete(key);
    }
  }

  function abortAllRequests() {
    controllers.forEach((controller) => {
      controller.abort();
    });
    controllers.clear();
  }

  async function triggerRefresh({ force = false, resetTimer = false } = {}) {
    if (!force && document.hidden) {
      return;
    }
    if (resetTimer) {
      resetAutoRefresh();
    }
    await onRefresh?.();
  }

  function handleVisibilityChange() {
    if (!refreshOnVisible || document.hidden) {
      return;
    }
    void triggerRefresh({ force: true, resetTimer: true });
  }

  onMounted(() => {
    if (autoStart) {
      startAutoRefresh();
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
  });

  onBeforeUnmount(() => {
    stopAutoRefresh();
    abortAllRequests();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
  });

  return {
    startAutoRefresh,
    stopAutoRefresh,
    resetAutoRefresh,
    createAbortSignal,
    clearAbortController,
    abortAllRequests,
    triggerRefresh,
  };
}
