import { useAutoRefresh as useAutoRefreshBase } from '../wip-shared/composables/useAutoRefresh.js';

export function useAutoRefresh(options = {}) {
  return useAutoRefreshBase(options);
}
