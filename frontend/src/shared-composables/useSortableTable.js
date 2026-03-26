import { computed, ref } from 'vue';

/**
 * Composable for client-side column sorting.
 *
 * @param {import('vue').Ref<Array>|import('vue').ComputedRef<Array>} data - reactive data array
 * @returns {{ sortKey, sortDirection, sortedData, setSortKey, toggleSort }}
 */
export function useSortableTable(data) {
  const sortKey = ref('');
  const sortDirection = ref('asc'); // 'asc' | 'desc'

  function detectType(value) {
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
  function normalizeDateStr(value) {
    const str = String(value).trim();
    // Replace slashes with dashes for consistent parsing
    // "2026/2/27 22:39:37" → "2026-2-27 22:39:37"
    const normalized = str.replace(/^(\d{4})\/(\d{1,2})\/(\d{1,2})/, '$1-$2-$3');
    const d = new Date(normalized);
    return Number.isNaN(d.getTime()) ? new Date(str) : d;
  }

  function compareValues(a, b, type) {
    if (a === null || a === undefined || a === '') return 1;
    if (b === null || b === undefined || b === '') return -1;

    if (type === 'number') {
      return Number(a) - Number(b);
    }
    if (type === 'date') {
      return normalizeDateStr(a) - normalizeDateStr(b);
    }
    // string — locale-aware
    return String(a).localeCompare(String(b), 'zh-Hant', { numeric: true, sensitivity: 'base' });
  }

  const sortedData = computed(() => {
    const rows = data.value ?? [];
    const key = sortKey.value;
    if (!key) {
      return rows;
    }

    const direction = sortDirection.value === 'asc' ? 1 : -1;

    // Detect type from first non-null value
    const firstRow = rows.find((r) => r[key] !== null && r[key] !== undefined && r[key] !== '');
    const type = firstRow ? detectType(firstRow[key]) : 'string';

    return [...rows].sort((a, b) => compareValues(a[key], b[key], type) * direction);
  });

  function setSortKey(key) {
    if (sortKey.value === key) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey.value = key;
      sortDirection.value = 'asc';
    }
  }

  function toggleSort(key) {
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
