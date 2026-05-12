import { useAutoRefresh as useAutoRefreshBase } from '../wip-shared/composables/useAutoRefresh';

export interface AutoRefreshOptions {
  onRefresh?: () => void | Promise<void>;
  intervalMs?: number;
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
