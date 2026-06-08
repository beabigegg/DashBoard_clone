/**
 * Hold cross-page navigation state via sessionStorage.
 */

const STORAGE_KEY = 'hold-nav-state';

export interface HoldNavigationState {
  holdType: string;
  reason: string[];
  workcenter: string | null;
  matrixPackage: string | null;
  // FilterPanel state
  workorder: string[];
  lotid: string[];
  package: string[];
  type: string[];
  firstname: string[];
  waferdesc: string[];
  workflow: string[];
  bop: string[];
  pjFunction: string[];
  ts: number;
}

export interface HoldPanelFilters {
  workorder?: string[];
  lotid?: string[];
  package?: string[];
  type?: string[];
  firstname?: string[];
  waferdesc?: string[];
  workflow?: string[];
  bop?: string[];
  pjFunction?: string[];
}

export function storeHoldNavigationState(
  holdType: string,
  reason: string[],
  workcenter: string | null = null,
  matrixPackage: string | null = null,
  panelFilters: HoldPanelFilters = {},
): void {
  try {
    const state: HoldNavigationState = {
      holdType: holdType || 'quality',
      reason: reason || [],
      workcenter: workcenter || null,
      matrixPackage: matrixPackage || null,
      workorder: panelFilters.workorder || [],
      lotid: panelFilters.lotid || [],
      package: panelFilters.package || [],
      type: panelFilters.type || [],
      firstname: panelFilters.firstname || [],
      waferdesc: panelFilters.waferdesc || [],
      workflow: panelFilters.workflow || [],
      bop: panelFilters.bop || [],
      pjFunction: panelFilters.pjFunction || [],
      ts: Date.now(),
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // sessionStorage unavailable — degrade gracefully
  }
}

export function loadHoldNavigationState(): HoldNavigationState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(STORAGE_KEY);
    const state = JSON.parse(raw) as HoldNavigationState;
    if (Date.now() - (state.ts || 0) > 5 * 60 * 1000) return null;
    return state;
  } catch {
    return null;
  }
}

/** Read the navigation state without consuming it (hold-detail uses this so hold-overview can still restore on back-navigation). */
export function peekHoldNavigationState(): HoldNavigationState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const state = JSON.parse(raw) as HoldNavigationState;
    if (Date.now() - (state.ts || 0) > 5 * 60 * 1000) return null;
    return state;
  } catch {
    return null;
  }
}

export function clearHoldNavigationState(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
