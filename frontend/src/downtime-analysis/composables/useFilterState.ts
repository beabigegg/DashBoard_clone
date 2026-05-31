import { reactive, computed } from 'vue';
import type { FilterState } from '../types';

const DEFAULT_STATE: FilterState = {
  workcenter_groups: [],
  families: [],
  resource_ids: [],
  package_groups: [],
  big_categories: [],
  status_types: [],
  start_date: '',
  end_date: '',
  granularity: 'day',
  is_production: false,
  is_key: false,
  is_monitor: false,
};

/**
 * useFilterState — manages filter state for downtime-analysis page.
 *
 * Cross-narrow behaviour (AC-6):
 * - Selecting equipment (resource_ids) narrows reason/category options.
 * - Equipment dropdown does NOT narrow itself (excludes self-narrowing per AC-6).
 */
export function useFilterState() {
  const state = reactive<FilterState>({ ...DEFAULT_STATE });

  /** Callbacks to notify when filter state changes (for cross-narrow). */
  const crossNarrowCallbacks: Array<(state: FilterState) => void> = [];

  function onCrossNarrow(cb: (state: FilterState) => void): void {
    crossNarrowCallbacks.push(cb);
  }

  function notifyCrossNarrow(): void {
    for (const cb of crossNarrowCallbacks) {
      cb({ ...state });
    }
  }

  function updateField<K extends keyof FilterState>(field: K, value: FilterState[K]): void {
    state[field] = value;
    notifyCrossNarrow();
  }

  function updateAll(next: Partial<FilterState>): void {
    for (const key of Object.keys(next) as Array<keyof FilterState>) {
      // Type-safe assignment
      (state as Record<string, unknown>)[key] = next[key];
    }
    notifyCrossNarrow();
  }

  function reset(): void {
    updateAll({ ...DEFAULT_STATE });
  }

  function setDefaultDates(): void {
    const today = new Date();
    const end = new Date(today);
    end.setDate(end.getDate() - 1);
    const start = new Date(end);
    start.setDate(start.getDate() - 6);
    // 7-day default: start = today-7, end = today-1
    state.start_date = start.toISOString().slice(0, 10);
    state.end_date = end.toISOString().slice(0, 10);
  }

  /** True when equipment filter is active (triggers cross-narrow). */
  const hasEquipmentFilter = computed(() => state.resource_ids.length > 0);

  /**
   * Build query body for POST /api/downtime-analysis/query.
   * Only include non-empty arrays.
   */
  function buildQueryBody(): Record<string, unknown> {
    const body: Record<string, unknown> = {
      start_date: state.start_date,
      end_date: state.end_date,
    };
    if (state.workcenter_groups.length > 0) body.workcenter_groups = state.workcenter_groups;
    if (state.families.length > 0) body.families = state.families;
    if (state.resource_ids.length > 0) body.resource_ids = state.resource_ids;
    if (state.package_groups.length > 0) body.package_groups = state.package_groups;
    if (state.big_categories.length > 0) body.big_categories = state.big_categories;
    if (state.status_types.length > 0) body.status_types = state.status_types;
    if (state.is_production) body.is_production = true;
    if (state.is_key) body.is_key = true;
    if (state.is_monitor) body.is_monitor = true;
    return body;
  }

  return {
    state,
    updateField,
    updateAll,
    reset,
    setDefaultDates,
    hasEquipmentFilter,
    buildQueryBody,
    onCrossNarrow,
  };
}
