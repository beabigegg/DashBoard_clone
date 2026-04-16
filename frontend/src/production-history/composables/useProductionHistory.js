import { ref, reactive, computed } from 'vue';
import { apiPost, apiGet } from '../../core/api.js';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling.js';
import { postExport } from '../../core/post-export.js';

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
    month: '',
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

  // ── Async job progress state ────────────────────────────────────────────────
  const jobProgress = reactive({
    active: false,
    jobId: null,
    status: '',
    progress: '',
    pct: 0,
  });

  let _jobAbortController = null;

  // ── Primary query ──────────────────────────────────────────────────────────
  async function runQuery(queryParams) {
    // Cancel any in-progress polling
    if (_jobAbortController) {
      _jobAbortController.abort();
      _jobAbortController = null;
    }
    jobProgress.active = false;

    loading.value = true;
    error.value = null;
    overloadError.value = null;
    expiredDataset.value = false;
    datasetId.value = null;

    try {
      const resp = await apiPost('/api/production-history/query', queryParams, { timeout: API_TIMEOUT });
      const respData = resp?.data || {};

      // ---- Async 202 path ----
      if (resp?._status === 202 || (respData.async === true && respData.job_id)) {
        const jobId = respData.job_id;
        const statusUrl = respData.status_url || `/api/production-history/job/${jobId}`;

        jobProgress.active = true;
        jobProgress.jobId = jobId;
        jobProgress.status = 'queued';
        jobProgress.progress = '';
        jobProgress.pct = 0;

        const controller = new AbortController();
        _jobAbortController = controller;

        try {
          await pollJobUntilComplete(statusUrl, {
            signal: controller.signal,
            onProgress: (statusResp) => {
              jobProgress.status = statusResp.status;
              jobProgress.progress = statusResp.progress || '';
              jobProgress.pct = statusResp.pct || 0;
            },
          });
        } finally {
          if (_jobAbortController === controller) _jobAbortController = null;
          jobProgress.active = false;
        }

        // Load view data using dataset_id returned from job
        const resolvedDatasetId = respData.dataset_id;
        if (resolvedDatasetId) {
          datasetId.value = resolvedDatasetId;
          _clearMatrixFilter();
          _clearSupplementaryFilter();
          await Promise.all([fetchPage(1), _fetchMatrix()]);
          fetchSupplementaryOptions();
        }
        return;
      }

      // ---- Sync 200 path ----
      const data = respData;
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
      if (err?.name === 'AbortError') {
        error.value = '查詢已取消';
      } else if (err?.errorCode === 'JOB_FAILED') {
        error.value = err?.message || '背景查詢失敗';
      } else if (err?.errorCode === 'JOB_POLL_TIMEOUT') {
        error.value = '背景查詢超時，請稍後重試';
      } else if (err.status === 503) {
        overloadError.value = {
          code: err.payload?.error?.code || 'SERVICE_UNAVAILABLE',
          retryAfterSeconds: err.retryAfterSeconds || 30,
        };
      } else {
        error.value = err.message || '查詢失敗，請稍後再試';
      }
    } finally {
      loading.value = false;
      jobProgress.active = false;
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
      month: filter.month || '',
    });
    // Only re-fetch detail table; the matrix itself stays unchanged to
    // preserve the full picture and just highlights the selected node/cell.
    await fetchPage(1);
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
    matrixFilter.month = '';
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

  // ── Export ─────────────────────────────────────────────────────────────────
  async function exportCsv() {
    if (!datasetId.value) return;
    const body = { dataset_id: datasetId.value };
    if (matrixFilter.workcenter_group) body.workcenter_group = matrixFilter.workcenter_group;
    if (matrixFilter.spec) body.spec = matrixFilter.spec;
    if (matrixFilter.equipment_id) body.equipment_id = matrixFilter.equipment_id;
    if (matrixFilter.month) body.month = matrixFilter.month;
    for (const [key, arr] of Object.entries(supplementaryFilter)) {
      if (arr.length) body[key] = arr;
    }
    await postExport('/api/production-history/export', body, `production-history-${datasetId.value}.csv`);
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
    jobProgress,
    runQuery,
    fetchPage,
    applyMatrixFilter,
    applySupplementaryFilter,
    exportCsv,
  };
}
