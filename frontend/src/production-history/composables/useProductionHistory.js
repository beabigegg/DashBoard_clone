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

  // Applied filter — sent to detail/matrix query endpoints
  const supplementaryFilter = reactive({
    work_orders: [],
    lot_ids: [],
    packages: [],
    bop_codes: [],
    workcenter_groups: [],
    equipment_ids: [],
  });

  // Staged filter — reflects what the user has selected in the UI but not yet
  // applied.  Triggers cross-filter option refresh; applied only on 查詢 click.
  const stagedFilter = reactive({
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

    const prevDatasetId = datasetId.value;

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
          if (resolvedDatasetId !== prevDatasetId) {
            _clearStagedFilter();
            _clearSupplementaryFilter();
          } else {
            _copyStagedToApplied();
          }
          await Promise.all([fetchPage(1), _fetchMatrix()]);
          fetchSupplementaryOptions(stagedFilter);
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
      _clearMatrixFilter();
      const datasetChanged = data.dataset_id !== prevDatasetId;
      if (datasetChanged) {
        _clearStagedFilter();
        _clearSupplementaryFilter();
      } else {
        _copyStagedToApplied();
      }
      // If applied filters are active, re-fetch filtered page+matrix.
      // (The primary query response always returns an unfiltered first page.)
      const hasActiveSuppFilter = Object.values(supplementaryFilter).some((arr) => arr.length > 0);
      if (!datasetChanged && hasActiveSuppFilter) {
        await Promise.all([fetchPage(1), _fetchMatrix()]);
      } else if (data.detail) {
        detailRows.value = data.detail.rows || [];
        pagination.value = data.detail.pagination || pagination.value;
      }
      fetchSupplementaryOptions(stagedFilter);
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
      const suppPayload = {};
      for (const [key, arr] of Object.entries(supplementaryFilter)) {
        if (arr.length) suppPayload[key] = arr;
      }
      const resp = await apiPost('/api/production-history/matrix', {
        dataset_id: datasetId.value,
        ...matrixFilter,
        ...suppPayload,
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

  function _clearStagedFilter() {
    stagedFilter.work_orders = [];
    stagedFilter.lot_ids = [];
    stagedFilter.packages = [];
    stagedFilter.bop_codes = [];
    stagedFilter.workcenter_groups = [];
    stagedFilter.equipment_ids = [];
  }

  function _copyStagedToApplied() {
    supplementaryFilter.work_orders = [...stagedFilter.work_orders];
    supplementaryFilter.lot_ids = [...stagedFilter.lot_ids];
    supplementaryFilter.packages = [...stagedFilter.packages];
    supplementaryFilter.bop_codes = [...stagedFilter.bop_codes];
    supplementaryFilter.workcenter_groups = [...stagedFilter.workcenter_groups];
    supplementaryFilter.equipment_ids = [...stagedFilter.equipment_ids];
  }

  // ── Supplementary options from spool (with cross-filter support) ───────────
  // filterParams: staged selections to narrow-down options (exclude-self per field)
  async function fetchSupplementaryOptions(filterParams = {}) {
    if (!datasetId.value) return;
    supplementaryOptionsLoading.value = true;
    try {
      const body = { dataset_id: datasetId.value };
      for (const [key, arr] of Object.entries(filterParams)) {
        if (Array.isArray(arr) && arr.length) body[key] = arr;
      }
      const resp = await apiPost('/api/production-history/options', body);
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

  // ── Stage a supplementary filter selection (no immediate query) ────────────
  // Updates the staged selection and re-fetches options with cross-filtering so
  // other dropdowns narrow to only compatible values.  Detail/matrix are NOT
  // updated until 查詢 is clicked.
  async function stageSupplementaryFilter(field, values) {
    stagedFilter[field] = values;
    await fetchSupplementaryOptions(stagedFilter);
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
    stagedFilter,
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
    stageSupplementaryFilter,
    exportCsv,
  };
}
