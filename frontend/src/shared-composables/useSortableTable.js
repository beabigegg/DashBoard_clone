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
      // ISO date-like strings
      if (/^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2})?/.test(value)) {
        return 'date';
      }
      // Numeric strings
      if (!Number.isNaN(Number(value)) && value.trim() !== '') {
        return 'number';
      }
    }
    return 'string';
  }

  function compareValues(a, b, type) {
    if (a === null || a === undefined || a === '') return 1;
    if (b === null || b === undefined || b === '') return -1;

    if (type === 'number') {
      return Number(a) - Number(b);
    }
    if (type === 'date') {
      return new Date(a) - new Date(b);
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
