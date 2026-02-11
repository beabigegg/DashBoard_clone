import { computed, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../../core/api.js';

ensureMesApiAvailable();

const NUMERIC_COLUMNS = new Set([
  'INPUT_QTY',
  'PRINT_DEFECT_QTY',
  'PRINT_DEFECT_RATE',
  'LEAD_DEFECT_QTY',
  'LEAD_DEFECT_RATE',
]);

function notify(level, message) {
  const toast = globalThis.Toast;
  if (toast && typeof toast[level] === 'function') {
    return toast[level](message);
  }
  if (level === 'error') {
    console.error(message);
  } else {
    console.info(message);
  }
  return null;
}

function dismissToast(id) {
  if (!id) return;
  const toast = globalThis.Toast;
  if (toast && typeof toast.dismiss === 'function') {
    toast.dismiss(id);
  }
}

function toComparable(value, key) {
  if (NUMERIC_COLUMNS.has(key)) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  if (value == null) return '';
  return String(value).toUpperCase();
}

function toDateString(date) {
  return date.toISOString().slice(0, 10);
}

export function useTmttDefectData() {
  const startDate = ref('');
  const endDate = ref('');
  const loading = ref(false);
  const errorMessage = ref('');
  const analysisData = ref(null);
  const activeFilter = ref(null);
  const sortState = ref({ column: '', asc: true });

  function initializeDateRange() {
    if (startDate.value && endDate.value) {
      return;
    }

    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 6);

    startDate.value = toDateString(start);
    endDate.value = toDateString(end);
  }

  const hasData = computed(() => Boolean(analysisData.value));
  const kpi = computed(() => analysisData.value?.kpi || null);
  const charts = computed(() => analysisData.value?.charts || {});
  const dailyTrend = computed(() => analysisData.value?.daily_trend || []);
  const rawDetailRows = computed(() => analysisData.value?.detail || []);

  const filteredRows = computed(() => {
    let rows = rawDetailRows.value;

    if (activeFilter.value?.field && activeFilter.value?.value) {
      rows = rows.filter((row) => String(row?.[activeFilter.value.field] || '') === activeFilter.value.value);
    }

    if (!sortState.value.column) {
      return rows;
    }

    const sorted = [...rows].sort((left, right) => {
      const leftValue = toComparable(left?.[sortState.value.column], sortState.value.column);
      const rightValue = toComparable(right?.[sortState.value.column], sortState.value.column);
      if (leftValue < rightValue) {
        return sortState.value.asc ? -1 : 1;
      }
      if (leftValue > rightValue) {
        return sortState.value.asc ? 1 : -1;
      }
      return 0;
    });

    return sorted;
  });

  const totalCount = computed(() => rawDetailRows.value.length);
  const filteredCount = computed(() => filteredRows.value.length);

  async function queryData() {
    if (!startDate.value || !endDate.value) {
      notify('warning', '請選擇起始和結束日期');
      return;
    }

    loading.value = true;
    errorMessage.value = '';
    const loadingToastId = notify('loading', '查詢中...');

    try {
      const result = await apiGet('/api/tmtt-defect/analysis', {
        params: {
          start_date: startDate.value,
          end_date: endDate.value,
        },
        timeout: 120000,
      });

      if (!result || !result.success) {
        const message = result?.error || '查詢失敗';
        errorMessage.value = message;
        notify('error', message);
        return;
      }

      analysisData.value = result.data;
      activeFilter.value = null;
      sortState.value = { column: '', asc: true };
      notify('success', '查詢完成');
    } catch (error) {
      const message = error?.message || '查詢失敗';
      errorMessage.value = message;
      notify('error', `查詢失敗: ${message}`);
    } finally {
      dismissToast(loadingToastId);
      loading.value = false;
    }
  }

  function setFilter({ field, value, label }) {
    if (!field || !value) {
      return;
    }
    activeFilter.value = {
      field,
      value,
      label: label || `${field}: ${value}`,
    };
  }

  function clearFilter() {
    activeFilter.value = null;
  }

  function toggleSort(column) {
    if (!column) {
      return;
    }

    if (sortState.value.column === column) {
      sortState.value = {
        column,
        asc: !sortState.value.asc,
      };
      return;
    }

    sortState.value = {
      column,
      asc: true,
    };
  }

  function exportCsv() {
    if (!startDate.value || !endDate.value) {
      notify('warning', '請先查詢資料');
      return;
    }

    const query = new URLSearchParams({
      start_date: startDate.value,
      end_date: endDate.value,
    });
    window.open(`/api/tmtt-defect/export?${query.toString()}`, '_blank', 'noopener');
  }

  initializeDateRange();

  return {
    startDate,
    endDate,
    loading,
    errorMessage,
    hasData,
    kpi,
    charts,
    dailyTrend,
    rawDetailRows,
    filteredRows,
    totalCount,
    filteredCount,
    activeFilter,
    sortState,
    queryData,
    setFilter,
    clearFilter,
    toggleSort,
    exportCsv,
  };
}
