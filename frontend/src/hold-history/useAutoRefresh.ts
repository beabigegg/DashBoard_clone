import { onUnmounted, ref } from 'vue';
import type { Ref } from 'vue';

/**
 * Auto-refresh composable — hold-history local implementation.
 *
 * API differs from shared-composables/useAutoRefresh (which targets wip-shared).
 * This version exposes { start, stop, lastRefreshAt, isStale, missCount } and
 * accepts fetchFn directly.  Keep as a separate module until a unified API is
 * agreed on across all features.
 *
 * Schedules repeated calls to fetchFn at intervalMs.
 * Pauses when document is hidden; resumes + fires immediately when visible again.
 * Retains last successful result and exposes a stale indicator on failure.
 */

export interface UseAutoRefreshOptions {
  intervalMs?: number;
  fetchFn: () => void | Promise<void>;
}

export interface UseAutoRefreshReturn {
  start: () => void;
  stop: () => void;
  lastRefreshAt: Ref<Date | null>;
  isStale: Ref<boolean>;
  missCount: Ref<number>;
}

export function useAutoRefresh({
  intervalMs = 60000,
  fetchFn,
}: UseAutoRefreshOptions): UseAutoRefreshReturn {
  const lastRefreshAt = ref<Date | null>(null);
  const isStale = ref(false);
  const missCount = ref(0);

  let timerId: ReturnType<typeof setTimeout> | null = null;
  let active = false;

  function schedule(): void {
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

  async function runFetch(): Promise<void> {
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

  function onVisibilityChange(): void {
    if (document.visibilityState === 'visible' && active) {
      if (timerId !== null) {
        clearTimeout(timerId);
        timerId = null;
      }
      void runFetch().then(() => {
        if (active) schedule();
      });
    }
  }

  function start(): void {
    if (active) return;
    active = true;
    isStale.value = false;
    missCount.value = 0;
    document.addEventListener('visibilitychange', onVisibilityChange);
    schedule();
  }

  function stop(): void {
    active = false;
    if (timerId !== null) {
      clearTimeout(timerId);
      timerId = null;
    }
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
