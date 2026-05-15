/**
 * First-tier filter composable for Production History.
 *
 * Manages the cached cross-filter options (Type / Package / BOP / Function)
 * and the wildcard text inputs (mfg_orders / lot_ids / wafer_lots).
 *
 * - Cross-filter: GET /api/production-history/filter-options?selected=<json>
 *   - Debounced (~200 ms) after selection changes
 *   - Empty selection returns full distinct sets (cached at mount)
 *   - Selections that disappear from the new option set are pruned
 *     automatically (PHF-01 fail-open picker — silently drop unknown values)
 *
 * - Multi-line parser: parseWildcardInput()
 *   - newline / comma / whitespace separated; trim; dedup; idempotent (AC-5)
 *   - Sends the raw `*` syntax to the backend (backend converts to LIKE bind
 *     per PHF-02; do NOT translate `*` to `%` here — defense-in-depth)
 *
 * Owns its own reactive state; App.vue composes it alongside
 * useProductionHistory.
 */

import { reactive, ref, watch } from 'vue';
import { apiGet } from '../../core/api';

// ── Types ──────────────────────────────────────────────────────────────────

/** Cross-filter selection — the four cached MultiSelect fields. */
export interface CachedFilterSelection {
  pj_types: string[];
  packages: string[];
  bops: string[];
  pj_functions: string[];
}

export type CachedFilterField = keyof CachedFilterSelection;

/** Wildcard text-input field — backed by a textarea, parsed via
 *  parseWildcardInput(). */
export type WildcardField = 'mfg_orders' | 'lot_ids' | 'wafer_lots';

/** GET /api/production-history/filter-options response payload. */
export interface FilterOptionsResponse {
  success: boolean;
  data: CachedFilterSelection;
  meta: {
    timestamp?: string;
    app_version?: string;
    updated_at?: string;
    schema_version?: number;
  };
}

interface ApiErrorLike {
  status?: number;
  message?: string;
}

// ── Public helpers ─────────────────────────────────────────────────────────

/** Parse a multi-line textarea into a deduplicated token list.
 *
 * - Separators: newline, comma, whitespace
 * - Trims whitespace from each token
 * - Removes empty tokens
 * - Deduplicates while preserving first-seen order
 * - Idempotent: parseWildcardInput(parseWildcardInput(x).join('\n')) yields
 *   the same array (AC-5)
 *
 * Does NOT translate `*` to `%` — that's a backend concern (PHF-02).
 * Sends the raw glob-style pattern to the server.
 */
export function parseWildcardInput(text: string | null | undefined): string[] {
  if (!text) return [];
  const tokens = String(text)
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const result: string[] = [];
  for (const token of tokens) {
    if (!seen.has(token)) {
      seen.add(token);
      result.push(token);
    }
  }
  return result;
}

// ── Composable ─────────────────────────────────────────────────────────────

const DEFAULT_DEBOUNCE_MS = 200;

export interface UseFirstTierFiltersOptions {
  /** GET endpoint for cross-filter options.  Override in tests. */
  endpoint?: string;
  /** Debounce window (ms) for cross-filter re-fetch.  Override in tests. */
  debounceMs?: number;
  /** Inject a custom fetcher for tests; defaults to apiGet. */
  fetcher?: (url: string) => Promise<unknown>;
}

export function useFirstTierFilters(options: UseFirstTierFiltersOptions = {}) {
  const endpoint = options.endpoint || '/api/production-history/filter-options';
  const debounceMs = options.debounceMs ?? DEFAULT_DEBOUNCE_MS;
  const fetcher = options.fetcher || ((url: string) => apiGet(url));

  // Cached unfiltered options (loaded once at mount, restored on full clear).
  const baseOptions = ref<CachedFilterSelection>({
    pj_types: [],
    packages: [],
    bops: [],
    pj_functions: [],
  });

  // Currently-displayed options (narrowed by the active selection).
  const options_ = ref<CachedFilterSelection>({
    pj_types: [],
    packages: [],
    bops: [],
    pj_functions: [],
  });

  // Active selection across the four cached fields.
  const selection = reactive<CachedFilterSelection>({
    pj_types: [],
    packages: [],
    bops: [],
    pj_functions: [],
  });

  // Snapshot of the last-committed selection per field. Used by commitSelection
  // to detect whether the user actually changed anything before closing a
  // dropdown (AC-4 no-op guard). Initialised to [] (matching selection init);
  // refreshed after every successful fetchFilterOptions so prune-driven
  // mutations do not trigger a spurious commit on the next dropdown close.
  const _lastCommitted: Record<CachedFilterField, string[]> = {
    pj_types: [],
    packages: [],
    bops: [],
    pj_functions: [],
  };

  // Wildcard textarea state.
  const wildcardInput = reactive<Record<WildcardField, string>>({
    mfg_orders: '',
    lot_ids: '',
    wafer_lots: '',
  });

  const loading = ref(false);
  const error = ref<string | null>(null);
  const lastUpdatedAt = ref<string | null>(null);
  // Names of fields whose selections were just auto-pruned by the most
  // recent cross-filter fetch. Surfaces silent fail-open drops to the UI
  // (UI-UX REC-02). Consumers clear this once they've displayed the notice
  // or when the user touches any selection.
  const prunedFields = ref<CachedFilterField[]>([]);

  let _debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let _inFlightToken = 0;

  /** Fire a single GET — call directly to bypass debouncing (tests, mount). */
  async function fetchFilterOptions(
    selected: Partial<CachedFilterSelection> = {},
  ): Promise<void> {
    const requestToken = ++_inFlightToken;
    loading.value = true;
    error.value = null;
    try {
      const url = _buildUrl(endpoint, selected);
      const resp = (await fetcher(url)) as FilterOptionsResponse;
      // Stale-response guard: a newer call already overwrote our state.
      if (requestToken !== _inFlightToken) return;
      const data = resp?.data || ({} as CachedFilterSelection);
      const next: CachedFilterSelection = {
        pj_types: Array.isArray(data.pj_types) ? data.pj_types : [],
        packages: Array.isArray(data.packages) ? data.packages : [],
        bops: Array.isArray(data.bops) ? data.bops : [],
        pj_functions: Array.isArray(data.pj_functions) ? data.pj_functions : [],
      };
      options_.value = next;
      lastUpdatedAt.value = resp?.meta?.updated_at || null;

      // Empty selection → snapshot as base options (the full distinct set).
      const isEmpty = !Object.values(selected).some(
        (arr) => Array.isArray(arr) && arr.length > 0,
      );
      if (isEmpty) {
        baseOptions.value = next;
      }

      // Prune any current selection that disappeared from the new option set
      // (fail-open picker: silently drop values no longer co-occurring).
      _pruneSelection(next);

      // Sync _lastCommitted to the post-prune selection so that a subsequent
      // dropdown close with no user changes is correctly treated as a no-op
      // (AC-4). Without this, a prune-driven value drop would make the next
      // commitSelection see a mismatch and fire a spurious cross-filter call.
      for (const f of ['pj_types', 'packages', 'bops', 'pj_functions'] as const) {
        _lastCommitted[f] = [...selection[f]];
      }
    } catch (err) {
      if (requestToken !== _inFlightToken) return;
      const e = err as ApiErrorLike;
      error.value = e?.message || '篩選選項載入失敗';
    } finally {
      if (requestToken === _inFlightToken) loading.value = false;
    }
  }

  /** Schedule a debounced cross-filter refresh. */
  function _scheduleRefresh(): void {
    if (_debounceTimer !== null) {
      clearTimeout(_debounceTimer);
      _debounceTimer = null;
    }
    _debounceTimer = setTimeout(() => {
      _debounceTimer = null;
      void fetchFilterOptions({
        pj_types: selection.pj_types,
        packages: selection.packages,
        bops: selection.bops,
        pj_functions: selection.pj_functions,
      });
    }, debounceMs);
  }

  /** Update one cached-filter field — buffer only; does NOT trigger a fetch.
   *
   * Callers (App.vue) should pair this with @update:modelValue and call
   * commitSelection(field) when the dropdown closes to apply the buffered
   * selection and fire the debounced cross-filter refresh (AC-1 / AC-2).
   */
  function setSelection(field: CachedFilterField, values: string[]): void {
    selection[field] = values;
    // User intent overrides any stale pruning notice from a prior fetch.
    if (prunedFields.value.length) prunedFields.value = [];
    // NOTE: _scheduleRefresh() intentionally removed — commits happen only at
    // dropdown-close via commitSelection() (fix-prod-history-multiselect-filter).
  }

  /** Apply the buffered selection for one field and schedule a cross-filter
   * refresh, but only when the committed value actually changed (AC-4 no-op).
   *
   * Called from App.vue on the @dropdown-close event of each first-tier
   * MultiSelect. Takes no `values` argument — reads from `selection[field]`
   * which is already up to date via setSelection().
   */
  function commitSelection(field: CachedFilterField): void {
    const current = selection[field];
    const last = _lastCommitted[field];
    // Shallow equality: same length + same value at every index.
    if (
      current.length === last.length &&
      current.every((v, i) => v === last[i])
    ) {
      return; // no-op: user changed nothing meaningful (AC-4)
    }
    _lastCommitted[field] = [...current];
    _scheduleRefresh();
  }

  /** Clear all cached-filter selections + wildcard textareas. */
  function clearAll(): void {
    selection.pj_types = [];
    selection.packages = [];
    selection.bops = [];
    selection.pj_functions = [];
    wildcardInput.mfg_orders = '';
    wildcardInput.lot_ids = '';
    wildcardInput.wafer_lots = '';
    options_.value = { ...baseOptions.value };
    prunedFields.value = [];
  }

  /** Parsed wildcard values for the current textarea state (one per field). */
  function parsedWildcards(): Record<WildcardField, string[]> {
    return {
      mfg_orders: parseWildcardInput(wildcardInput.mfg_orders),
      lot_ids: parseWildcardInput(wildcardInput.lot_ids),
      wafer_lots: parseWildcardInput(wildcardInput.wafer_lots),
    };
  }

  /** Build the request-payload fragment for the main /query endpoint.
   *  Returns only non-empty fields (backward compat with Type-only flow). */
  function buildQueryFragment(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    if (selection.pj_types.length) out.pj_types = selection.pj_types;
    if (selection.packages.length) out.pj_packages = selection.packages;
    if (selection.bops.length) out.pj_bops = selection.bops;
    if (selection.pj_functions.length) out.pj_functions = selection.pj_functions;
    const w = parsedWildcards();
    if (w.mfg_orders.length) out.mfg_orders = w.mfg_orders;
    if (w.lot_ids.length) out.lot_ids = w.lot_ids;
    if (w.wafer_lots.length) out.wafer_lots = w.wafer_lots;
    return out;
  }

  function _pruneSelection(next: CachedFilterSelection): void {
    const dropped: CachedFilterField[] = [];
    const prune = (field: CachedFilterField, allowed: string[]): void => {
      const before = selection[field];
      const after = before.filter((v) => allowed.includes(v));
      if (after.length !== before.length) dropped.push(field);
      selection[field] = after;
    };
    prune('pj_types', next.pj_types);
    prune('packages', next.packages);
    prune('bops', next.bops);
    prune('pj_functions', next.pj_functions);
    if (dropped.length) prunedFields.value = dropped;
  }

  /** Clear the pruned-fields notice (called after the UI surfaces it, or
   *  when the user manually changes a selection). */
  function clearPrunedFields(): void {
    if (prunedFields.value.length) prunedFields.value = [];
  }

  // Stop pending debounce when the consumer unmounts (best-effort cleanup
  // through a watcher on the timer — App.vue may invoke clearAll() instead).
  watch(loading, () => {
    // intentionally empty — placeholder to keep the watcher alive for tests
    // that exercise reactivity timing.
  });

  return {
    // state
    baseOptions,
    options: options_,
    selection,
    wildcardInput,
    loading,
    error,
    lastUpdatedAt,
    prunedFields,
    // actions
    fetchFilterOptions,
    setSelection,
    commitSelection,
    clearAll,
    clearPrunedFields,
    parsedWildcards,
    buildQueryFragment,
  };
}

// ── URL builder (exported for tests) ───────────────────────────────────────

export function _buildUrl(
  endpoint: string,
  selected: Partial<CachedFilterSelection>,
): string {
  // Only include non-empty fields to keep the URL short.
  const trimmed: Partial<CachedFilterSelection> = {};
  for (const key of ['pj_types', 'packages', 'bops', 'pj_functions'] as const) {
    const arr = selected[key];
    if (Array.isArray(arr) && arr.length > 0) trimmed[key] = arr;
  }
  if (Object.keys(trimmed).length === 0) return endpoint;
  const encoded = encodeURIComponent(JSON.stringify(trimmed));
  return `${endpoint}?selected=${encoded}`;
}
