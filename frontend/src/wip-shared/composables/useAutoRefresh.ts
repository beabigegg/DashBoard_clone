import { onBeforeUnmount, onMounted } from 'vue';

import type { AutoRefreshOptions } from '../../shared-composables/useAutoRefresh';

const DEFAULT_REFRESH_INTERVAL_MS = 10 * 60 * 1000;
const JITTER_FACTOR = 0.15; // ±15% random jitter to prevent synchronized requests

function jitteredInterval(baseMs: number): number {
  const jitter = baseMs * JITTER_FACTOR * (2 * Math.random() - 1);
  return Math.max(1000, Math.round(baseMs + jitter));
}

export function useAutoRefresh({
  onRefresh,
  intervalMs = DEFAULT_REFRESH_INTERVAL_MS,
  autoStart = true,
  refreshOnVisible = true,
}: AutoRefreshOptions = {}) {
  let refreshTimer: ReturnType<typeof setTimeout> | null = null;
  const controllers = new Map<string, AbortController>();
  let pageHideHandler: (() => void) | null = null;

  function stopAutoRefresh(): void {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function scheduleNextRefresh(): void {
    stopAutoRefresh();
    refreshTimer = setTimeout(() => {
      if (!document.hidden) {
        void onRefresh?.();
      }
      scheduleNextRefresh();
    }, jitteredInterval(intervalMs));
  }

  function startAutoRefresh(): void {
    scheduleNextRefresh();
  }

  function resetAutoRefresh(): void {
    startAutoRefresh();
  }

  function createAbortSignal(key = 'default'): AbortSignal {
    const previous = controllers.get(key);
    if (previous) {
      previous.abort();
    }

    const controller = new AbortController();
    controllers.set(key, controller);
    return controller.signal;
  }

  function clearAbortController(key = 'default'): void {
    const controller = controllers.get(key);
    if (controller) {
      controller.abort();
      controllers.delete(key);
    }
  }

  function abortAllRequests(): void {
    controllers.forEach((controller) => {
      controller.abort();
    });
    controllers.clear();
  }

  async function triggerRefresh({ force = false, resetTimer = false } = {}): Promise<void> {
    if (!force && document.hidden) {
      return;
    }
    if (resetTimer) {
      resetAutoRefresh();
    }
    await onRefresh?.();
  }

  function handleVisibilityChange(): void {
    if (!refreshOnVisible || document.hidden) {
      return;
    }
    void triggerRefresh({ force: true, resetTimer: true });
  }

  onMounted(() => {
    pageHideHandler = () => {
      stopAutoRefresh();
      abortAllRequests();
    };

    if (autoStart) {
      startAutoRefresh();
    }
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('pagehide', pageHideHandler);
  });

  onBeforeUnmount(() => {
    stopAutoRefresh();
    abortAllRequests();
    document.removeEventListener('visibilitychange', handleVisibilityChange);
    if (pageHideHandler) {
      window.removeEventListener('pagehide', pageHideHandler);
      pageHideHandler = null;
    }
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
