import { computed, ref, type ComputedRef, type Ref } from 'vue';

// ── Selection descriptor ───────────────────────────────────────────────────

export type CrossFilterSource = 'ring' | 'heatmap' | 'matrix' | 'alerts' | 'summary';

export interface CrossFilterSelection<T = Record<string, unknown>> {
  /** Stable key that identifies which chart owns this selection. One per source. */
  source: CrossFilterSource;
  /** Human-readable label for the clear-all button display. */
  label: string;
  /** Predicate applied during AND-intersection; returns true if the row matches. */
  predicate: (row: T) => boolean;
}

// ── Composable ─────────────────────────────────────────────────────────────

export interface UseCrossFilterReturn<T> {
  /** Ordered list of active selections (one per source at most). */
  activeSelections: Ref<CrossFilterSelection<T>[]>;
  /** AND-intersection of all active predicates over allEquipment. */
  filteredEquipment: ComputedRef<T[]>;
  /** True when at least one selection is active. */
  hasActiveSelections: ComputedRef<boolean>;
  /**
   * Add a selection for the given source. If that source already has an entry,
   * re-adding it toggles (removes) it — clearing it. This is the re-click toggle.
   */
  addSelection: (sel: CrossFilterSelection<T>) => void;
  /** Remove the selection contributed by the given source key. */
  removeSelection: (source: CrossFilterSource | string) => void;
  /** Remove all active selections. */
  clearAll: () => void;
  /**
   * Returns the input data set for a given chart.
   * Excludes that chart's own selection from the intersection (exclude-self),
   * so the chart's own dimension always shows all available values from peer
   * selections only.
   */
  getInputForChart: (source: CrossFilterSource | string) => ComputedRef<T[]>;
}

export function useCrossFilter<T>(
  allEquipment: Ref<T[]>
): UseCrossFilterReturn<T> {
  const activeSelections = ref<CrossFilterSelection<T>[]>([]) as Ref<CrossFilterSelection<T>[]>;

  // AND-intersection of all active selections
  const filteredEquipment = computed<T[]>(() => {
    const sels = activeSelections.value;
    if (sels.length === 0) return allEquipment.value;
    return allEquipment.value.filter((row) => sels.every((sel) => sel.predicate(row)));
  });

  const hasActiveSelections = computed<boolean>(() => activeSelections.value.length > 0);

  function addSelection(sel: CrossFilterSelection<T>): void {
    const existing = activeSelections.value.findIndex((s) => s.source === sel.source);
    if (existing >= 0) {
      // Toggle off (re-click)
      activeSelections.value = activeSelections.value.filter((_, i) => i !== existing);
    } else {
      activeSelections.value = [...activeSelections.value, sel];
    }
  }

  function removeSelection(source: CrossFilterSource | string): void {
    activeSelections.value = activeSelections.value.filter((s) => s.source !== source);
  }

  function clearAll(): void {
    activeSelections.value = [];
  }

  function getInputForChart(source: CrossFilterSource | string): ComputedRef<T[]> {
    return computed<T[]>(() => {
      const peerSels = activeSelections.value.filter((s) => s.source !== source);
      if (peerSels.length === 0) return allEquipment.value;
      return allEquipment.value.filter((row) => peerSels.every((sel) => sel.predicate(row)));
    });
  }

  return {
    activeSelections,
    filteredEquipment,
    hasActiveSelections,
    addSelection,
    removeSelection,
    clearAll,
    getInputForChart,
  };
}
