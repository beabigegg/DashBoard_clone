import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, apiUpload, ensureMesApiAvailable } from '../../core/api.js';
import { replaceRuntimeHistory } from '../../core/shell-navigation.js';

ensureMesApiAvailable();

function parseArrayQuery(params, key) {
  const repeated = params.getAll(key).map((item) => String(item || '').trim()).filter(Boolean);
  if (repeated.length > 0) {
    return repeated;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildQueryString(filters) {
  const params = new URLSearchParams();
  if (filters.tableName) params.set('table_name', filters.tableName);
  if (filters.searchColumn) params.set('search_column', filters.searchColumn);
  if (filters.excelColumn) params.set('excel_column', filters.excelColumn);
  if (filters.queryType) params.set('query_type', filters.queryType);
  if (filters.dateColumn) params.set('date_column', filters.dateColumn);
  if (filters.dateFrom) params.set('date_from', filters.dateFrom);
  if (filters.dateTo) params.set('date_to', filters.dateTo);
  return params.toString();
}

export function useExcelQueryData() {
  const uploadState = reactive({
    fileName: '',
    uploading: false,
    uploaded: false,
  });
  const loading = reactive({
    tables: false,
    values: false,
    metadata: false,
    querying: false,
    exporting: false,
  });
  const errorMessage = ref('');
  const successMessage = ref('');

  const excelColumns = ref([]);
  const excelPreview = ref([]);
  const excelColumnValues = ref([]);
  const detectedColumnType = ref('');

  const tableOptions = ref([]);
  const tableMetadata = ref(null);

  const filters = reactive({
    excelColumn: '',
    tableName: '',
    searchColumn: '',
    returnColumns: [],
    queryType: 'in',
    dateColumn: '',
    dateFrom: '',
    dateTo: '',
  });

  const queryResult = reactive({
    rows: [],
    columns: [],
    total: 0,
  });

  const tableColumns = computed(() => {
    const columns = tableMetadata.value?.columns;
    if (!Array.isArray(columns)) {
      return [];
    }
    return columns;
  });

  const availableReturnColumns = computed(() => tableColumns.value.map((item) => item.name));

  const isDateRangeEnabled = computed(() => Boolean(tableMetadata.value?.time_field));

  function hydrateFiltersFromUrl() {
    const params = new URLSearchParams(window.location.search);
    filters.tableName = String(params.get('table_name') || '').trim();
    filters.searchColumn = String(params.get('search_column') || '').trim();
    filters.excelColumn = String(params.get('excel_column') || '').trim();
    filters.queryType = String(params.get('query_type') || 'in').trim() || 'in';
    filters.dateColumn = String(params.get('date_column') || '').trim();
    filters.dateFrom = String(params.get('date_from') || '').trim();
    filters.dateTo = String(params.get('date_to') || '').trim();
    filters.returnColumns = parseArrayQuery(params, 'return_columns');
  }

  function syncUrlState() {
    const params = new URLSearchParams(buildQueryString(filters));
    filters.returnColumns.forEach((item) => params.append('return_columns', item));
    const query = params.toString();
    replaceRuntimeHistory(query ? `/excel-query?${query}` : '/excel-query');
  }

  function resetResult() {
    queryResult.rows = [];
    queryResult.columns = [];
    queryResult.total = 0;
  }

  async function loadTables() {
    loading.tables = true;
    errorMessage.value = '';
    try {
      const payload = await apiGet('/api/excel-query/tables', { timeout: 60000, silent: true });
      tableOptions.value = Array.isArray(payload?.tables) ? payload.tables : [];
    } catch (error) {
      errorMessage.value = error?.message || '載入資料表選單失敗';
      tableOptions.value = [];
    } finally {
      loading.tables = false;
    }
  }

  async function uploadExcel(file) {
    if (!file) {
      errorMessage.value = '請先選擇 Excel 檔案';
      return false;
    }
    uploadState.uploading = true;
    errorMessage.value = '';
    successMessage.value = '';
    resetResult();
    try {
      const formData = new FormData();
      formData.append('file', file);
      const payload = await apiUpload('/api/excel-query/upload', formData, { timeout: 360000, silent: true });
      excelColumns.value = Array.isArray(payload?.columns) ? payload.columns : [];
      excelPreview.value = Array.isArray(payload?.preview) ? payload.preview : [];
      uploadState.fileName = String(file.name || '');
      uploadState.uploaded = true;
      successMessage.value = `檔案上傳完成，共 ${Number(payload?.total_rows || 0)} 筆`;
      if (excelColumns.value.length > 0 && !filters.excelColumn) {
        filters.excelColumn = excelColumns.value[0];
      }
      return true;
    } catch (error) {
      uploadState.uploaded = false;
      errorMessage.value = error?.message || '檔案上傳失敗';
      return false;
    } finally {
      uploadState.uploading = false;
    }
  }

  async function loadExcelColumnValues() {
    if (!filters.excelColumn) {
      excelColumnValues.value = [];
      detectedColumnType.value = '';
      return;
    }
    loading.values = true;
    errorMessage.value = '';
    try {
      const [valuesPayload, typePayload] = await Promise.all([
        apiPost('/api/excel-query/column-values', { column_name: filters.excelColumn }, { timeout: 60000, silent: true }),
        apiPost('/api/excel-query/column-type', { column_name: filters.excelColumn }, { timeout: 60000, silent: true }),
      ]);
      excelColumnValues.value = Array.isArray(valuesPayload?.values) ? valuesPayload.values : [];
      detectedColumnType.value = String(typePayload?.type_label || typePayload?.detected_type || '').trim();
    } catch (error) {
      errorMessage.value = error?.message || '讀取 Excel 欄位資訊失敗';
      excelColumnValues.value = [];
      detectedColumnType.value = '';
    } finally {
      loading.values = false;
    }
  }

  async function loadTableMetadata() {
    if (!filters.tableName) {
      tableMetadata.value = null;
      filters.searchColumn = '';
      filters.returnColumns = [];
      filters.dateColumn = '';
      return;
    }
    loading.metadata = true;
    errorMessage.value = '';
    try {
      const payload = await apiPost(
        '/api/excel-query/table-metadata',
        { table_name: filters.tableName },
        { timeout: 60000, silent: true },
      );
      tableMetadata.value = payload;

      const columns = Array.isArray(payload?.columns) ? payload.columns : [];
      const columnNames = columns.map((item) => item.name);
      if (!columnNames.includes(filters.searchColumn)) {
        filters.searchColumn = columnNames[0] || '';
      }
      if (!Array.isArray(filters.returnColumns) || filters.returnColumns.length === 0) {
        filters.returnColumns = columnNames.slice(0, Math.min(8, columnNames.length));
      } else {
        filters.returnColumns = filters.returnColumns.filter((item) => columnNames.includes(item));
      }
      filters.dateColumn = String(payload?.time_field || '').trim();
    } catch (error) {
      tableMetadata.value = null;
      filters.searchColumn = '';
      filters.returnColumns = [];
      filters.dateColumn = '';
      errorMessage.value = error?.message || '讀取資料表欄位失敗';
    } finally {
      loading.metadata = false;
    }
  }

  async function executeQuery() {
    errorMessage.value = '';
    successMessage.value = '';
    resetResult();

    if (!uploadState.uploaded) {
      errorMessage.value = '請先上傳 Excel 檔案';
      return false;
    }
    if (!filters.tableName || !filters.searchColumn || filters.returnColumns.length === 0) {
      errorMessage.value = '請補齊查詢條件（資料表/查詢欄位/回傳欄位）';
      return false;
    }
    if (excelColumnValues.value.length === 0) {
      errorMessage.value = '請先選擇 Excel 欄位並載入查詢值';
      return false;
    }
    if ((filters.dateFrom && !filters.dateTo) || (!filters.dateFrom && filters.dateTo)) {
      errorMessage.value = '日期範圍需同時提供起訖日期';
      return false;
    }

    loading.querying = true;
    syncUrlState();
    try {
      const payload = await apiPost(
        '/api/excel-query/execute-advanced',
        {
          table_name: filters.tableName,
          search_column: filters.searchColumn,
          return_columns: filters.returnColumns,
          search_values: excelColumnValues.value,
          query_type: filters.queryType,
          date_column: filters.dateColumn || undefined,
          date_from: filters.dateFrom || undefined,
          date_to: filters.dateTo || undefined,
        },
        { timeout: 360000, silent: true },
      );
      queryResult.rows = Array.isArray(payload?.data) ? payload.data : [];
      queryResult.columns = Array.isArray(payload?.columns) ? payload.columns : filters.returnColumns;
      queryResult.total = Number(payload?.total || queryResult.rows.length || 0);
      successMessage.value = `查詢完成，共 ${queryResult.total} 筆`;
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '查詢失敗';
      return false;
    } finally {
      loading.querying = false;
    }
  }

  async function exportCsv() {
    if (queryResult.rows.length === 0) {
      errorMessage.value = '目前無可匯出資料，請先執行查詢';
      return false;
    }
    loading.exporting = true;
    errorMessage.value = '';
    try {
      const response = await fetch('/api/excel-query/export-csv', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          table_name: filters.tableName,
          search_column: filters.searchColumn,
          return_columns: queryResult.columns.length > 0 ? queryResult.columns : filters.returnColumns,
          search_values: excelColumnValues.value,
        }),
      });
      if (!response.ok) {
        let message = `匯出失敗 (${response.status})`;
        try {
          const payload = await response.json();
          message = payload?.error || payload?.message || message;
        } catch {
          // ignore parse error
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const href = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = href;
      anchor.download = `excel-query-${filters.tableName || 'result'}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(href);
      successMessage.value = 'CSV 匯出成功';
      return true;
    } catch (error) {
      errorMessage.value = error?.message || '匯出失敗';
      return false;
    } finally {
      loading.exporting = false;
    }
  }

  return {
    uploadState,
    loading,
    errorMessage,
    successMessage,
    excelColumns,
    excelPreview,
    excelColumnValues,
    detectedColumnType,
    tableOptions,
    tableMetadata,
    tableColumns,
    filters,
    queryResult,
    availableReturnColumns,
    isDateRangeEnabled,
    hydrateFiltersFromUrl,
    loadTables,
    uploadExcel,
    loadExcelColumnValues,
    loadTableMetadata,
    executeQuery,
    exportCsv,
  };
}
