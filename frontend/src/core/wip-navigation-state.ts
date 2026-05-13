/**
 * WIP cross-page navigation state via sessionStorage.
 */

const STORAGE_KEY = 'wip-nav-state';

export interface WipNavigationFilters {
  workorder?: unknown[];
  lotid?: unknown[];
  package?: unknown[];
  type?: unknown[];
  firstname?: unknown[];
  waferdesc?: unknown[];
  workflow?: unknown[];
  bop?: unknown[];
  pjFunction?: unknown[];
  matrixPackage?: string;
  [key: string]: unknown[] | string | undefined;
}

export interface WipNavigationState {
  workorder: unknown[];
  lotid: unknown[];
  package: unknown[];
  type: unknown[];
  firstname: unknown[];
  waferdesc: unknown[];
  workflow: unknown[];
  bop: unknown[];
  pjFunction: unknown[];
  matrixPackage: string;
  status: string | null;
  ts: number;
}

/**
 * Store filter state for cross-page navigation.
 * @param filters - { workorder, lotid, package, type, firstname, waferdesc }
 * @param status - active status filter
 */
export function storeWipNavigationState(
  filters: WipNavigationFilters,
  status: string | null = null
): void {
  try {
    const state: WipNavigationState = {
      workorder: filters.workorder || [],
      lotid: filters.lotid || [],
      package: filters.package || [],
      type: filters.type || [],
      firstname: filters.firstname || [],
      waferdesc: filters.waferdesc || [],
      workflow: filters.workflow || [],
      bop: filters.bop || [],
      pjFunction: filters.pjFunction || [],
      matrixPackage: typeof filters.matrixPackage === 'string' ? filters.matrixPackage : '',
      status: status || null,
      ts: Date.now(),
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // sessionStorage full or unavailable — degrade gracefully
  }
}

/**
 * Load and consume the stored navigation state.
 * Returns null if no state exists or if the state is older than 5 minutes.
 * The state is removed after reading to prevent stale reuse.
 */
export function loadWipNavigationState(): WipNavigationState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    sessionStorage.removeItem(STORAGE_KEY);

    const state = JSON.parse(raw) as WipNavigationState;
    // Expire after 5 minutes to avoid stale state on accidental reloads
    if (Date.now() - (state.ts || 0) > 5 * 60 * 1000) {
      return null;
    }
    return state;
  } catch {
    return null;
  }
}

/**
 * Clear any pending navigation state (e.g., on page unload without navigation).
 */
export function clearWipNavigationState(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
