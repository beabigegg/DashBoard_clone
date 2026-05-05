import { computed, ref } from 'vue';
import type { Ref, ComputedRef } from 'vue';

export type SortDirection = 'asc' | 'desc';
export type SortType = 'string' | 'number' | 'date';

export type DataRow = Record<string, unknown>;

export interface SortableTableComposable<T extends DataRow = DataRow> {
  sortKey: Ref<string>;
  sortDirection: Ref<SortDirection>;
  sortedData: ComputedRef<T[]>;
  setSortKey: (key: string) => void;
  toggleSort: (key: string) => void;
}

/**
 * Composable for client-side column sorting.
 *
 * @param data - reactive data array
 * @returns { sortKey, sortDirection, sortedData, setSortKey, toggleSort }
 */
export function useSortableTable<T extends DataRow = DataRow>(
  data: Ref<T[]> | ComputedRef<T[]>,
): SortableTableComposable<T> {
  const sortKey: Ref<string> = ref('');
  const sortDirection: Ref<SortDirection> = ref('asc');

  function detectType(value: unknown): SortType {
    if (value === null || value === undefined || value === '') {
      return 'string';
    }
    if (typeof value === 'number') {
      return 'number';
    }
    if (value instanceof Date) {
      return 'date';
    }
    if (typeof value === 'string') {
      // Date-like strings: YYYY-MM-DD, YYYY/M/D, with optional time
      if (/^\d{4}[-/]\d{1,2}[-/]\d{1,2}([ T]\d{1,2}:\d{2})?/.test(value)) {
        return 'date';
      }
      // Numeric strings
      if (!Number.isNaN(Number(value)) && value.trim() !== '') {
        return 'number';
      }
    }
    return 'string';
  }

  /**
   * Normalize a date string to ensure reliable parsing.
   * Handles YYYY/M/D, YYYY-M-D, with optional time components.
   */
  function normalizeDateStr(value: unknown): Date {
    const str = String(value).trim();
    // Replace slashes with dashes for consistent parsing
    // "2026/2/27 22:39:37" → "2026-2-27 22:39:37"
    const normalized = str.replace(/^(\d{4})\/(\d{1,2})\/(\d{1,2})/, '$1-$2-$3');
    const d = new Date(normalized);
    return Number.isNaN(d.getTime()) ? new Date(str) : d;
  }

  function compareValues(a: unknown, b: unknown, type: SortType): number {
    if (a === null || a === undefined || a === '') return 1;
    if (b === null || b === undefined || b === '') return -1;

    if (type === 'number') {
      return Number(a) - Number(b);
    }
    if (type === 'date') {
      return normalizeDateStr(a).getTime() - normalizeDateStr(b).getTime();
    }
    // string — locale-aware
    return String(a).localeCompare(String(b), 'zh-Hant', { numeric: true, sensitivity: 'base' });
  }

  const sortedData: ComputedRef<T[]> = computed(() => {
    const rows = data.value ?? [];
    const key = sortKey.value;
    if (!key) {
      return rows;
    }

    const direction = sortDirection.value === 'asc' ? 1 : -1;

    // Detect type from first non-null value
    const firstRow = rows.find((r) => r[key] !== null && r[key] !== undefined && r[key] !== '');
    const type: SortType = firstRow ? detectType(firstRow[key]) : 'string';

    return [...rows].sort((a, b) => compareValues(a[key], b[key], type) * direction);
  });

  function setSortKey(key: string): void {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey.value = key;
      sortDirection.value = 'asc';
    }
  }

  function toggleSort(key: string): void {
    setSortKey(key);
  }

  return {
    sortKey,
    sortDirection,
    sortedData,
    setSortKey,
    toggleSort,
  };
}
