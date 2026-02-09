import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../../core/api.js';

const QUERY_LIMIT = 1000;

function normalizeTableConfig(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return {};
  }
  return payload;
}

function toDisplayError(error, fallback) {
  return error?.message || fallback;
}

function toTableModel(table) {
  return {
    name: String(table?.name || ''),
    display_name: String(table?.display_name || table?.name || ''),
    time_field: table?.time_field || null,
    row_count: Number(table?.row_count || 0),
    description: String(table?.description || ''),
  };
}

export function useTableData() {
  const tableConfig = ref({});
  const selectedTable = ref(null);
  const columns = ref([]);
  const rows = ref([]);
  const rowCount = ref(0);
  const hasQueried = ref(false);
  const filters = reactive({});

  const loadingConfig = ref(false);
  const loadingColumns = ref(false);
  const loadingQuery = ref(false);

  const pageError = ref('');
  const viewerError = ref('');

  const activeFilterCount = computed(() => {
    return Object.values(filters).filter((value) => String(value ?? '').trim().length > 0).length;
  });

  async function loadTableConfig() {
    loadingConfig.value = true;
    pageError.value = '';

    try {
      const response = await apiGet('/api/get_table_info');
      const payload = response?.success ? response.data : response;
      tableConfig.value = normalizeTableConfig(payload);
    } catch (error) {
      pageError.value = toDisplayError(error, '載入表格設定失敗');
    } finally {
      loadingConfig.value = false;
    }
  }

  function clearFilters() {
    for (const key of Object.keys(filters)) {
      delete filters[key];
    }
  }

  function setFilter(column, value) {
    const trimmed = String(value ?? '').trim();
    if (!trimmed) {
      delete filters[column];
      return;
    }
    filters[column] = trimmed;
  }

  function removeFilter(column) {
    delete filters[column];
  }

  function resetViewerState() {
    columns.value = [];
    rows.value = [];
    rowCount.value = 0;
    hasQueried.value = false;
    viewerError.value = '';
    clearFilters();
  }

  async function loadColumns() {
    if (!selectedTable.value?.name) {
      return;
    }

    loadingColumns.value = true;
    viewerError.value = '';

    try {
      const response = await apiPost('/api/get_table_columns', {
        table_name: selectedTable.value.name,
      });

      if (response?.error) {
        throw new Error(String(response.error));
      }

      columns.value = Array.isArray(response?.columns) ? response.columns : [];
    } catch (error) {
      columns.value = [];
      viewerError.value = toDisplayError(error, '載入欄位資訊失敗');
    } finally {
      loadingColumns.value = false;
    }
  }

  async function selectTable(table) {
    if (!table?.name) {
      return;
    }

    selectedTable.value = toTableModel(table);
    resetViewerState();
    await loadColumns();
  }

  function buildFilterPayload() {
    const payload = {};
    for (const column of columns.value) {
      const value = String(filters[column] ?? '').trim();
      if (value) {
        payload[column] = value;
      }
    }
    return payload;
  }

  async function queryTable() {
    if (!selectedTable.value?.name) {
      return;
    }

    hasQueried.value = true;
    loadingQuery.value = true;
    viewerError.value = '';

    try {
      const queryFilters = buildFilterPayload();
      const response = await apiPost('/api/query_table', {
        table_name: selectedTable.value.name,
        limit: QUERY_LIMIT,
        time_field: selectedTable.value.time_field,
        filters: Object.keys(queryFilters).length > 0 ? queryFilters : null,
      });

      if (response?.error) {
        throw new Error(String(response.error));
      }

      rows.value = Array.isArray(response?.data) ? response.data : [];
      rowCount.value = Number.isFinite(Number(response?.row_count))
        ? Number(response.row_count)
        : rows.value.length;
    } catch (error) {
      rows.value = [];
      rowCount.value = 0;
      viewerError.value = toDisplayError(error, '查詢失敗');
    } finally {
      loadingQuery.value = false;
    }
  }

  function closeViewer() {
    selectedTable.value = null;
    resetViewerState();
  }

  return {
    tableConfig,
    selectedTable,
    columns,
    filters,
    rows,
    rowCount,
    hasQueried,
    loadingConfig,
    loadingColumns,
    loadingQuery,
    pageError,
    viewerError,
    activeFilterCount,
    loadTableConfig,
    selectTable,
    setFilter,
    removeFilter,
    clearFilters,
    queryTable,
    closeViewer,
  };
}
