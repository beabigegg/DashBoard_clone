import { ref, reactive, computed } from 'vue';
import { apiPost, apiGet } from '../../core/api.js';

const API_TIMEOUT = 360000;

export function useProductionHistory() {
  // ── Query state ────────────────────────────────────────────────────────────
  const loading = ref(false);
  const error = ref(null);
  const datasetId = ref(null);
  const datasetMeta = ref(null);

  // ── Matrix state ───────────────────────────────────────────────────────────
  const matrixTree = ref([]);
  const matrixMonthColumns = ref([]);
  const matrixLoading = ref(false);

  // ── Active matrix filter ───────────────────────────────────────────────────
  const matrixFilter = reactive({
    workcenter_group: '',
    spec: '',
    equipment_id: '',
  });

  // ── Supplementary filter options & selections ─────────────────────────────
  const supplementaryOptions = ref({
    work_orders: [],
    lot_ids: [],
    packages: [],
    bop_codes: [],
    workcenter_groups: [],
    equipment_ids: [],
  });

  const supplementaryFilter = reactive({
    work_orders: [],
    lot_ids: [],
    packages: [],
    bop_codes: [],
    workcenter_groups: [],
    equipment_ids: [],
  });

  const supplementaryOptionsLoading = ref(false);

  // ── Detail table state ─────────────────────────────────────────────────────
  const detailRows = ref([]);
  const pagination = ref({ page: 1, per_page: 25, total_rows: 0, total_pages: 0 });
  const detailLoading = ref(false);

  // ── Overload/expire error state ────────────────────────────────────────────
  const overloadError = ref(null);   // { code, retryAfterSeconds }
  const expiredDataset = ref(false);

  // ── Primary query ──────────────────────────────────────────────────────────
  async function runQuery(queryParams) {
    loading.value = true;
    error.value = null;
    overloadError.value = null;
    expiredDataset.value = false;
    datasetId.value = null;

    try {
      const resp = await apiPost('/api/production-history/query', queryParams, { timeout: API_TIMEOUT });
      const data = resp.data;
      datasetId.value = data.dataset_id;
      datasetMeta.value = resp.meta || null;

      if (data.matrix) {
        matrixTree.value = data.matrix.tree || [];
        matrixMonthColumns.value = data.matrix.month_columns || [];
      }
      if (data.detail) {
        detailRows.value = data.detail.rows || [];
        pagination.value = data.detail.pagination || pagination.value;
      }
      _clearMatrixFilter();
      _clearSupplementaryFilter();
      fetchSupplementaryOptions();
    } catch (err) {
      if (err.status === 503) {
        overloadError.value = {
          code: err.payload?.error?.code || 'SERVICE_UNAVAILABLE',
          retryAfterSeconds: err.retryAfterSeconds || 30,
        };
      } else {
        error.value = err.message || '查詢失敗，請稍後再試';
      }
    } finally {
      loading.value = false;
    }
  }

  // ── Page navigation ────────────────────────────────────────────────────────
  async function fetchPage(page) {
    if (!datasetId.value) return;
    detailLoading.value = true;
    expiredDataset.value = false;
    try {
      // Build supplementary filter payload (only send non-empty arrays)
      const suppPayload = {};
      for (const [key, arr] of Object.entries(supplementaryFilter)) {
        if (arr.length) suppPayload[key] = arr;
      }

      const resp = await apiPost('/api/production-history/page', {
        dataset_id: datasetId.value,
        page,
        per_page: pagination.value.per_page,
        ...matrixFilter,
        ...suppPayload,
      });
      detailRows.value = resp.data.rows || [];
      pagination.value = resp.data.pagination || pagination.value;
    } catch (err) {
      if (err.status === 410) {
        expiredDataset.value = true;
      } else if (err.status === 503) {
        overloadError.value = {
          code: err.payload?.error?.code || 'SERVICE_UNAVAILABLE',
          retryAfterSeconds: err.retryAfterSeconds || 30,
        };
      } else {
        error.value = err.message || '分頁查詢失敗';
      }
    } finally {
      detailLoading.value = false;
    }
  }

  // ── Matrix filter + re-fetch detail ───────────────────────────────────────
  async function applyMatrixFilter(filter) {
    Object.assign(matrixFilter, {
      workcenter_group: filter.workcenter_group || '',
      spec: filter.spec || '',
      equipment_id: filter.equipment_id || '',
    });
    await fetchPage(1);
    await _fetchMatrix();
  }

  async function _fetchMatrix() {
    if (!datasetId.value) return;
    matrixLoading.value = true;
    try {
      const resp = await apiPost('/api/production-history/matrix', {
        dataset_id: datasetId.value,
        ...matrixFilter,
      });
      matrixTree.value = resp.data.tree || [];
      matrixMonthColumns.value = resp.data.month_columns || [];
    } catch (err) {
      if (err.status === 410) {
        expiredDataset.value = true;
      }
    } finally {
      matrixLoading.value = false;
    }
  }

  function _clearMatrixFilter() {
    matrixFilter.workcenter_group = '';
    matrixFilter.spec = '';
    matrixFilter.equipment_id = '';
  }

  function _clearSupplementaryFilter() {
    supplementaryFilter.work_orders = [];
    supplementaryFilter.lot_ids = [];
    supplementaryFilter.packages = [];
    supplementaryFilter.bop_codes = [];
    supplementaryFilter.workcenter_groups = [];
    supplementaryFilter.equipment_ids = [];
  }

  // ── Supplementary options from spool ────────────────────────────────────────
  async function fetchSupplementaryOptions() {
    if (!datasetId.value) return;
    supplementaryOptionsLoading.value = true;
    try {
      const resp = await apiPost('/api/production-history/options', {
        dataset_id: datasetId.value,
      });
      const d = resp.data || {};
      supplementaryOptions.value = {
        work_orders: d.work_orders || [],
        lot_ids: d.lot_ids || [],
        packages: d.packages || [],
        bop_codes: d.bop_codes || [],
        workcenter_groups: d.workcenter_groups || [],
        equipment_ids: d.equipment_ids || [],
      };
    } catch (_) {
      // non-critical — dropdowns stay empty
    } finally {
      supplementaryOptionsLoading.value = false;
    }
  }

  // ── Apply supplementary filter and re-fetch page ──────────────────────────
  async function applySupplementaryFilter(field, values) {
    supplementaryFilter[field] = values;
    await fetchPage(1);
  }

  // ── Export URL ─────────────────────────────────────────────────────────────
  function buildExportUrl() {
    if (!datasetId.value) return null;
    const params = new URLSearchParams({ dataset_id: datasetId.value });
    if (matrixFilter.workcenter_group) params.set('workcenter_group', matrixFilter.workcenter_group);
    if (matrixFilter.spec) params.set('spec', matrixFilter.spec);
    if (matrixFilter.equipment_id) params.set('equipment_id', matrixFilter.equipment_id);
    for (const [key, arr] of Object.entries(supplementaryFilter)) {
      if (arr.length) params.set(key, arr.join(','));
    }
    return `/api/production-history/export?${params}`;
  }

  return {
    loading,
    error,
    datasetId,
    datasetMeta,
    matrixTree,
    matrixMonthColumns,
    matrixLoading,
    matrixFilter,
    supplementaryOptions,
    supplementaryFilter,
    supplementaryOptionsLoading,
    detailRows,
    pagination,
    detailLoading,
    overloadError,
    expiredDataset,
    runQuery,
    fetchPage,
    applyMatrixFilter,
    applySupplementaryFilter,
    buildExportUrl,
  };
}
