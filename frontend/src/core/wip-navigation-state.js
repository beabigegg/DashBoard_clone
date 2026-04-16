/**
 * WIP cross-page navigation state via sessionStorage.
 *
 * When filter sets are large (many lotids, workorders, etc.), URL query params
 * can exceed Gunicorn's limit_request_line (4094). This module stores the bulk
 * filter state in sessionStorage so only lightweight params (workcenter, status)
 * need to appear in the URL.
 *
 * Flow:
 *   overview → detail: storeWipNavigationState(filters) then navigate with ?workcenter=X
 *   detail → overview: storeWipNavigationState(filters) then navigate to /wip-overview
 *   on page load: loadWipNavigationState() to recover filters
 */

const STORAGE_KEY = 'wip-nav-state';

/**
 * Store filter state for cross-page navigation.
 * @param {Object} filters - { workorder, lotid, package, type, firstname, waferdesc }
 * @param {string|null} status - active status filter
 */
export function storeWipNavigationState(filters, status = null) {
  try {
    const state = {
      workorder: filters.workorder || [],
      lotid: filters.lotid || [],
      package: filters.package || [],
      type: filters.type || [],
      firstname: filters.firstname || [],
      waferdesc: filters.waferdesc || [],
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
export function loadWipNavigationState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    sessionStorage.removeItem(STORAGE_KEY);

    const state = JSON.parse(raw);
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
export function clearWipNavigationState() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
