import { ref, reactive } from 'vue';
import { apiPost } from '../../core/api';
import { pollJobUntilComplete } from '../../shared-composables/useAsyncJobPolling';
import { postExport } from '../../core/post-export';

const API_TIMEOUT = 360000;

// ── Public types ───────────────────────────────────────────────────────────

/** Matrix filter — single-row dimensions narrowed by matrix click. */
export interface MatrixFilter {
  workcenter_group: string;
  spec: string;
  equipment_id: string;
  month: string;
}

/** Supplementary filter — multi-value dropdown selections.
 *
 * Per D6 (prod-history-first-tier-cache-filters), MFGORDERNAME / CONTAINERNAME
 * (lot_ids) / Package / BOP / Function were promoted to the first-tier filter
 * panel (cached cross-filter or wildcard textareas).  This interface now only
 * carries the still-spool-derived fields: WorkCenter 群組 + Equipment.
 */
export interface SupplementaryFilter {
  workcenter_groups: string[];
  equipment_ids: string[];
}

/** Field key used by stageSupplementaryFilter. */
export type SupplementaryFilterField = keyof SupplementaryFilter;

/** Options list available per supplementary-filter field. */
export interface SupplementaryOptions {
  workcenter_groups: string[];
  equipment_ids: string[];
}

/** Pagination payload returned by the page endpoint. */
export interface Pagination {
  page: number;
  per_page: number;
  total_rows: number;
  total_pages: number;
}

/** One row of the production-history detail table.
 *
 * Raw per-partial track-out row (data-shape §3.4) — one row per
 * LOTWIPHISTORY partial track-out, not aggregated. `trackin_*` /
 * `trackout_*` carry raw per-partial values (previously MIN/MAX/SUM aggregates).
 * `pj_function` is sourced from `DWH.DW_MES_CONTAINER.PJ_FUNCTION` and is
 * surfaced as the "PJ Function" detail-table column / "Function" CSV column.
 */
export interface DetailRow {
  lot_id: string | null;
  pj_type: string | null;
  bop: string | null;
  pj_function: string | null;
  work_order: string | null;
  wafer_lot: string | null;
  package_name: string | null;
  workcenter: string | null;
  spec: string | null;
  equipment_id: string | null;
  equipment_name: string | null;
  trackin_time: string | null;
  trackout_time: string | null;
  trackin_qty: number | null;
  trackout_qty: number | null;
  [key: string]: unknown;
}

/** Leaf node (equipment). */
export interface MatrixEquipmentNode {
  label: string;
  equipment_name?: string | null;
  count: number;
  month_counts?: Record<string, number>;
}

/** Spec node — parent of equipment leaves. */
export interface MatrixSpecNode {
  label: string;
  count: number;
  month_counts?: Record<string, number>;
  children?: MatrixEquipmentNode[];
}

/** Workcenter-group node — top-level. */
export interface MatrixWorkcenterNode {
  label: string;
  count: number;
  month_counts?: Record<string, number>;
  children?: MatrixSpecNode[];
}

/** Tree returned by /matrix and embedded in /query response. */
export type MatrixTree = MatrixWorkcenterNode[];

/** 503-overload error payload surfaced to the UI. */
export interface OverloadError {
  code: string;
  retryAfterSeconds: number;
}

/** Async-job progress state surfaced to the UI. */
export interface JobProgressState {
  active: boolean;
  jobId: string | null;
  status: string;
  progress: string;
  pct: number;
}

/** Dataset metadata (echoed from the response envelope's `meta`). */
export type DatasetMeta = Record<string, unknown> | null;

/** Primary query body (submitted by App.vue). */
export interface QueryParams {
  pj_types?: string[];
  /** Cached MultiSelect — D7 first-tier filters. */
  pj_packages?: string[];
  pj_bops?: string[];
  pj_functions?: string[];
  /** Wildcard textarea fields — backend re-validates per PHF-02. */
  mfg_orders?: string[];
  lot_ids?: string[];
  wafer_lots?: string[];
  start_date: string;
  end_date: string;
  [key: string]: unknown;
}

// ── Internal helper types ─────────────────────────────────────────────────

interface QueryResponseEnvelope {
  _status?: number;
  data?: QueryResponseData;
  meta?: DatasetMeta;
}

interface QueryResponseData {
  async?: boolean;
  job_id?: string;
  status_url?: string;
  dataset_id?: string;
  matrix?: { tree?: MatrixTree; month_columns?: string[] };
  detail?: { rows?: DetailRow[]; pagination?: Pagination };
}

interface ApiErrorLike {
  name?: string;
  message?: string;
  status?: number;
  errorCode?: string;
  retryAfterSeconds?: number;
  payload?: { error?: { code?: string } };
}

export function useProductionHistory() {
  // ── Query state ────────────────────────────────────────────────────────────
  const loading = ref(false);
  const error = ref<string | null>(null);
  const datasetId = ref<string | null>(null);
  const datasetMeta = ref<DatasetMeta>(null);

  // ── Matrix state ───────────────────────────────────────────────────────────
  const matrixTree = ref<MatrixTree>([]);
  const matrixMonthColumns = ref<string[]>([]);
  const matrixLoading = ref(false);

  // ── Active matrix filter ───────────────────────────────────────────────────
  const matrixFilter = reactive<MatrixFilter>({
    workcenter_group: '',
    spec: '',
    equipment_id: '',
    month: '',
  });

  // ── Supplementary filter options & selections ─────────────────────────────
  const supplementaryOptions = ref<SupplementaryOptions>({
    workcenter_groups: [],
    equipment_ids: [],
  });

  // Applied filter — sent to detail/matrix query endpoints
  const supplementaryFilter = reactive<SupplementaryFilter>({
    workcenter_groups: [],
    equipment_ids: [],
  });

  // Staged filter — reflects what the user has selected in the UI but not yet
  // applied.  Triggers cross-filter option refresh; applied only on 查詢 click.
  const stagedFilter = reactive<SupplementaryFilter>({
    workcenter_groups: [],
    equipment_ids: [],
  });

  const supplementaryOptionsLoading = ref(false);

  // ── Detail table state ─────────────────────────────────────────────────────
  const detailRows = ref<DetailRow[]>([]);
  const pagination = ref<Pagination>({ page: 1, per_page: 25, total_rows: 0, total_pages: 0 });
  const detailLoading = ref(false);

  // ── Overload/expire error state ────────────────────────────────────────────
  const overloadError = ref<OverloadError | null>(null);
  const expiredDataset = ref(false);

  // ── Async job progress state ────────────────────────────────────────────────
  const jobProgress = reactive<JobProgressState>({
    active: false,
    jobId: null,
    status: '',
    progress: '',
    pct: 0,
  });

  let _jobAbortController: AbortController | null = null;

  // ── Primary query ──────────────────────────────────────────────────────────
  async function runQuery(queryParams: QueryParams): Promise<void> {
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
      const resp = (await apiPost('/api/production-history/query', queryParams, {
        timeout: API_TIMEOUT,
      })) as QueryResponseEnvelope;
      const respData: QueryResponseData = resp?.data || {};

      // ---- Async 202 path ----
      if (resp?._status === 202 || (respData.async === true && respData.job_id)) {
        const jobId = respData.job_id as string;
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
              jobProgress.progress = (statusResp.progress as string) || '';
              jobProgress.pct = (statusResp.pct as number) || 0;
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
      datasetId.value = data.dataset_id ?? null;
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
      const hasActiveSuppFilter = Object.values(supplementaryFilter).some(
        (arr) => (arr as string[]).length > 0,
      );
      if (!datasetChanged && hasActiveSuppFilter) {
        await Promise.all([fetchPage(1), _fetchMatrix()]);
      } else if (data.detail) {
        detailRows.value = data.detail.rows || [];
        pagination.value = data.detail.pagination || pagination.value;
      }
      fetchSupplementaryOptions(stagedFilter);
    } catch (err) {
      const e = err as ApiErrorLike;
      if (e?.name === 'AbortError') {
        error.value = '查詢已取消';
      } else if (e?.errorCode === 'JOB_FAILED') {
        error.value = e?.message || '背景查詢失敗';
      } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
        error.value = '背景查詢超時，請稍後重試';
      } else if (e.status === 503) {
        overloadError.value = {
          code: e.payload?.error?.code || 'SERVICE_UNAVAILABLE',
          retryAfterSeconds: e.retryAfterSeconds || 30,
        };
      } else {
        error.value = e.message || '查詢失敗，請稍後再試';
      }
    } finally {
      loading.value = false;
      jobProgress.active = false;
    }
  }

  // ── Page navigation ────────────────────────────────────────────────────────
  async function fetchPage(page: number): Promise<void> {
    if (!datasetId.value) return;
    detailLoading.value = true;
    expiredDataset.value = false;
    try {
      // Build supplementary filter payload (only send non-empty arrays)
      const suppPayload: Partial<SupplementaryFilter> = {};
      for (const [key, arr] of Object.entries(supplementaryFilter) as [
        SupplementaryFilterField,
        string[],
      ][]) {
        if (arr.length) suppPayload[key] = arr;
      }

      const resp = (await apiPost('/api/production-history/page', {
        dataset_id: datasetId.value,
        page,
        per_page: pagination.value.per_page,
        ...matrixFilter,
        ...suppPayload,
      })) as { data: { rows?: DetailRow[]; pagination?: Pagination } };
      detailRows.value = resp.data.rows || [];
      pagination.value = resp.data.pagination || pagination.value;
    } catch (err) {
      const e = err as ApiErrorLike;
      if (e.status === 410) {
        expiredDataset.value = true;
      } else if (e.status === 503) {
        overloadError.value = {
          code: e.payload?.error?.code || 'SERVICE_UNAVAILABLE',
          retryAfterSeconds: e.retryAfterSeconds || 30,
        };
      } else {
        error.value = e.message || '分頁查詢失敗';
      }
    } finally {
      detailLoading.value = false;
    }
  }

  // ── Matrix filter + re-fetch detail ───────────────────────────────────────
  async function applyMatrixFilter(filter: Partial<MatrixFilter>): Promise<void> {
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

  async function _fetchMatrix(): Promise<void> {
    if (!datasetId.value) return;
    matrixLoading.value = true;
    try {
      const suppPayload: Partial<SupplementaryFilter> = {};
      for (const [key, arr] of Object.entries(supplementaryFilter) as [
        SupplementaryFilterField,
        string[],
      ][]) {
        if (arr.length) suppPayload[key] = arr;
      }
      const resp = (await apiPost('/api/production-history/matrix', {
        dataset_id: datasetId.value,
        ...matrixFilter,
        ...suppPayload,
      })) as { data: { tree?: MatrixTree; month_columns?: string[] } };
      matrixTree.value = resp.data.tree || [];
      matrixMonthColumns.value = resp.data.month_columns || [];
    } catch (err) {
      const e = err as ApiErrorLike;
      if (e.status === 410) {
        expiredDataset.value = true;
      }
    } finally {
      matrixLoading.value = false;
    }
  }

  function _clearMatrixFilter(): void {
    matrixFilter.workcenter_group = '';
    matrixFilter.spec = '';
    matrixFilter.equipment_id = '';
    matrixFilter.month = '';
  }

  function _clearSupplementaryFilter(): void {
    supplementaryFilter.workcenter_groups = [];
    supplementaryFilter.equipment_ids = [];
  }

  function _clearStagedFilter(): void {
    stagedFilter.workcenter_groups = [];
    stagedFilter.equipment_ids = [];
  }

  function _copyStagedToApplied(): void {
    supplementaryFilter.workcenter_groups = [...stagedFilter.workcenter_groups];
    supplementaryFilter.equipment_ids = [...stagedFilter.equipment_ids];
  }

  // ── Supplementary options from spool (with cross-filter support) ───────────
  // filterParams: staged selections to narrow-down options (exclude-self per field)
  async function fetchSupplementaryOptions(
    filterParams: Partial<SupplementaryFilter> = {},
  ): Promise<void> {
    if (!datasetId.value) return;
    supplementaryOptionsLoading.value = true;
    try {
      const body: Record<string, unknown> = { dataset_id: datasetId.value };
      for (const [key, arr] of Object.entries(filterParams)) {
        if (Array.isArray(arr) && arr.length) body[key] = arr;
      }
      const resp = (await apiPost('/api/production-history/options', body)) as {
        data?: Partial<SupplementaryOptions>;
      };
      const d = resp.data || {};
      supplementaryOptions.value = {
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
  async function stageSupplementaryFilter(
    field: SupplementaryFilterField,
    values: string[],
  ): Promise<void> {
    stagedFilter[field] = values;
    await fetchSupplementaryOptions(stagedFilter);
  }

  // ── Export ─────────────────────────────────────────────────────────────────
  async function exportCsv(): Promise<void> {
    if (!datasetId.value) return;
    const body: Record<string, unknown> = { dataset_id: datasetId.value };
    if (matrixFilter.workcenter_group) body.workcenter_group = matrixFilter.workcenter_group;
    if (matrixFilter.spec) body.spec = matrixFilter.spec;
    if (matrixFilter.equipment_id) body.equipment_id = matrixFilter.equipment_id;
    if (matrixFilter.month) body.month = matrixFilter.month;
    for (const [key, arr] of Object.entries(supplementaryFilter)) {
      if ((arr as string[]).length) body[key] = arr;
    }
    await postExport(
      '/api/production-history/export',
      body,
      `production-history-${datasetId.value}.csv`,
    );
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
