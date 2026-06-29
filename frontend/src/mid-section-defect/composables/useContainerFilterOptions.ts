/**
 * Cross-filter composable for MSD Type (PJ_TYPE) and Package (PRODUCTLINENAME)
 * filter dimensions.
 *
 * - Fetches narrowed option lists from GET /api/mid-section-defect/container-filter-options
 * - Re-fetch is triggered via commit() only when a dropdown closes (mirrors
 *   useFirstTierFilters setSelection/commitSelection pattern).  The watch-based
 *   approach fired on every single toggleOption click and prevented multi-select.
 * - 200 ms debounced re-fetch inside commit()
 * - Stale-response guard via in-flight token
 */

import { ref, type Ref } from 'vue';
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
    } catch {
      if (requestToken !== _inFlightToken) return;
      // Fail-open: leave existing options intact; no throw.
    } finally {
      if (requestToken === _inFlightToken) isLoading.value = false;
    }
  }

  /** Schedule a debounced re-fetch.  Called from commit() on dropdown-close. */
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

  /**
   * Trigger a debounced cross-filter re-fetch.
   *
   * Call this from App.vue on the @dropdown-close event of the Type or Package
   * MultiSelect — NOT on @update:model-value.  Calling on every modelValue change
   * would fire after each individual click and prevent multi-select.
   */
  function commit(): void {
    _scheduleRefresh();
  }

  // Initial fetch on composable setup (no selection yet → returns full option sets).
  void fetchOptions();

  return { pjTypeOptions, packageOptions, isLoading, fetchOptions, commit };
}
