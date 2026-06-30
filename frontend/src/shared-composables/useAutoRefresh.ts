import { useAutoRefresh as useAutoRefreshBase } from '../wip-shared/composables/useAutoRefresh';

export interface AutoRefreshOptions {
  onRefresh?: () => void | Promise<void>;
  /**
   * Refresh interval in ms. Pass a number for a fixed interval, or a getter
   * `() => number` to make each scheduling cycle re-read a dynamic value (e.g.
   * a poll interval aligned to a backend-reported cadence). The getter is
   * evaluated once per scheduled tick.
   */
  intervalMs?: number | (() => number);
  autoStart?: boolean;
  refreshOnVisible?: boolean;
  [key: string]: unknown;
}

export interface AutoRefreshComposable {
  startAutoRefresh: () => void;
  stopAutoRefresh: () => void;
  resetAutoRefresh: () => void;
  createAbortSignal: (key?: string) => AbortSignal;
  clearAbortController: (key?: string) => void;
  abortAllRequests: () => void;
  triggerRefresh: (options?: { force?: boolean; resetTimer?: boolean }) => Promise<void>;
}

export function useAutoRefresh(options: AutoRefreshOptions = {}): AutoRefreshComposable {
  return useAutoRefreshBase(options) as AutoRefreshComposable;
}
