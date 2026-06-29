/**
 * Cross-filter composable for MSD Type (PJ_TYPE) and Package (PRODUCTLINENAME)
 * filter dimensions.
 *
 * - Fetches narrowed option lists from GET /api/mid-section-defect/container-filter-options
 * - 200 ms debounced re-fetch on selection change (mirrors useFirstTierFilters AC-2 guard)
 * - Stale-response guard via in-flight token
 * - Syncs _lastCommitted after each fetch (snapshot-diff pattern from frontend-patterns.md)
 *
 * Accepts external Ref<string[]> args so that App.vue drives the selection state
 * and this composable is purely responsible for keeping option lists fresh.
 */

import { ref, watch, type Ref } from 'vue';
import { apiGet } from '../../core/api';

const DEFAULT_DEBOUNCE_MS = 200;

export interface ContainerFilterOptionsData {
  pj_types: string[];
  packages: string[];
}

interface ApiResult {
  success?: boolean;
  data?: ContainerFilterOptionsData;
}

export interface UseContainerFilterOptionsOpts {
  /** Override endpoint (useful in tests). */
  endpoint?: string;
  /** Override debounce window in ms. Defaults to 200. */
  debounceMs?: number;
  /** Inject a custom fetcher for tests; defaults to apiGet. */
  fetcher?: (url: string) => Promise<unknown>;
}

/** Build the GET URL for container-filter-options, encoding only non-empty selections. */
export function _buildContainerFilterUrl(
  endpoint: string,
  selectedPjTypes: string[],
  selectedPackages: string[],
): string {
  const selected: Record<string, string[]> = {};
  if (selectedPjTypes.length) selected.pj_types = selectedPjTypes;
  if (selectedPackages.length) selected.packages = selectedPackages;
  if (Object.keys(selected).length === 0) return endpoint;
  return `${endpoint}?selected=${encodeURIComponent(JSON.stringify(selected))}`;
}

export function useContainerFilterOptions(
  selectedPjTypes: Ref<string[]>,
  selectedPackages: Ref<string[]>,
  opts: UseContainerFilterOptionsOpts = {},
) {
  const endpoint = opts.endpoint ?? '/api/mid-section-defect/container-filter-options';
  const debounceMs = opts.debounceMs ?? DEFAULT_DEBOUNCE_MS;
  const fetcher = opts.fetcher ?? ((url: string) => apiGet(url));

  const pjTypeOptions = ref<string[]>([]);
  const packageOptions = ref<string[]>([]);
  const isLoading = ref(false);

  // Track last-fetched selection to avoid spurious re-fetches on reactive mutations
  // that do not reflect a true user-initiated change (snapshot-diff pattern).
  const _lastCommitted = {
    pj_types: [] as string[],
    packages: [] as string[],
  };

  let _debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let _inFlightToken = 0;

  async function fetchOptions(): Promise<void> {
    const requestToken = ++_inFlightToken;
    isLoading.value = true;
    try {
      const url = _buildContainerFilterUrl(
        endpoint,
        selectedPjTypes.value,
        selectedPackages.value,
      );
      const result = (await fetcher(url)) as ApiResult | null;
      if (requestToken !== _inFlightToken) return; // stale response; newer call in-flight
      if (result?.success && result.data) {
        pjTypeOptions.value = Array.isArray(result.data.pj_types) ? result.data.pj_types : [];
        packageOptions.value = Array.isArray(result.data.packages) ? result.data.packages : [];
      }
      // Sync _lastCommitted so the next watch tick does not trigger a spurious re-fetch.
      _lastCommitted.pj_types = [...selectedPjTypes.value];
      _lastCommitted.packages = [...selectedPackages.value];
    } catch {
      if (requestToken !== _inFlightToken) return;
      // Fail-open: leave existing options intact; no throw.
    } finally {
      if (requestToken === _inFlightToken) isLoading.value = false;
    }
  }

  function _scheduleRefresh(): void {
    if (_debounceTimer !== null) {
      clearTimeout(_debounceTimer);
      _debounceTimer = null;
    }
    _debounceTimer = setTimeout(() => {
      _debounceTimer = null;
      void fetchOptions();
    }, debounceMs);
  }

  // Watch selectedPjTypes → re-fetch (narrows packageOptions); no-op when unchanged.
  watch(
    selectedPjTypes,
    (now) => {
      const last = _lastCommitted.pj_types;
      if (now.length === last.length && now.every((v, i) => v === last[i])) return;
      _scheduleRefresh();
    },
    { deep: true },
  );

  // Watch selectedPackages → re-fetch (narrows pjTypeOptions); no-op when unchanged.
  watch(
    selectedPackages,
    (now) => {
      const last = _lastCommitted.packages;
      if (now.length === last.length && now.every((v, i) => v === last[i])) return;
      _scheduleRefresh();
    },
    { deep: true },
  );

  // Initial fetch on composable setup.
  void fetchOptions();

  return { pjTypeOptions, packageOptions, isLoading, fetchOptions };
}
