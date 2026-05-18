<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';

import { apiGet, apiPost } from '../core/api';
import { parseMultiLineInput } from '../core/reject-history-filters';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';

// ---- Local interfaces ----
interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

interface QualityMeta {
  status?: string;
  max_rows?: number | string | null;
}

interface MaterialTraceFilterOptions {
  workcenter_groups?: string[];
}

interface MaterialTraceQueryPayload {
  rows?: Record<string, unknown>[];
  pagination?: Pagination;
  meta?: {
    unresolved?: string[];
    max_rows?: number | string | null;
    [key: string]: unknown;
  };
  quality_meta?: QualityMeta;
  query_hash?: string | null;
  async?: boolean;
  job_id?: string;
}

interface MaterialTraceJobStatus {
  status?: string;
  error?: string;
}

const API_TIMEOUT = 60000;
const DEFAULT_PER_PAGE = 20;
const FORWARD_INPUT_LIMIT = 200;
const REVERSE_INPUT_LIMIT = 50;

// ---- Query mode state ----
const queryMode = ref<'forward' | 'reverse'>('forward');
const forwardInputType = ref<'lot' | 'workorder'>('lot');
const inputText = ref<string>('');

// ---- Filter state ----
const workcenterGroupOptions = ref<string[]>([]);
const selectedWorkcenterGroups = ref<string[]>([]);
const workcenterDropdownOpen = ref<boolean>(false);
const workcenterSearch = ref<string>('');

// ---- Result state ----
const rows = ref<Record<string, unknown>[]>([]);
const pagination = ref<Pagination>({ page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 0 });
const loading = ref<boolean>(false);
const paginationLoading = ref<boolean>(false);
const errorMessage = ref<string>('');
const warningMessage = ref<string>('');
const unresolvedWarning = ref<string>('');

// ---- Async job state (task 8.3) ----
const currentQueryHash = ref<string | null>(null);
const pollingJobId = ref<string | null>(null);
const _POLL_INTERVAL_MS = 2000;
const _POLL_MAX_ATTEMPTS = 150; // ~5 minutes
let _pollingAttempts = 0;
let _pollingTimer: ReturnType<typeof setTimeout> | null = null;

// ---- Computed ----
const parsedValues = computed(() => parseMultiLineInput(inputText.value));
const inputCount = computed(() => parsedValues.value.length);
const currentInputLimit = computed(() =>
  queryMode.value === 'forward' ? FORWARD_INPUT_LIMIT : REVERSE_INPUT_LIMIT,
);
const isOverLimit = computed(() => inputCount.value > currentInputLimit.value);
const hasResults = computed(() => rows.value.length > 0);
const canQuery = computed(
  () => inputCount.value > 0 && !isOverLimit.value && !loading.value && !paginationLoading.value,
);
const canExport = computed(() => hasResults.value && !loading.value && !paginationLoading.value);

const queryModeForApi = computed(() => {
  if (queryMode.value === 'reverse') return 'material_lot';
  return forwardInputType.value; // 'lot' or 'workorder'
});

const filteredWorkcenterOptions = computed(() => {
  const q = workcenterSearch.value.toLowerCase().trim();
  if (!q) return workcenterGroupOptions.value;
  return workcenterGroupOptions.value.filter((g) => g.toLowerCase().includes(q));
});

const workcenterTriggerText = computed(() => {
  if (selectedWorkcenterGroups.value.length === 0) return '全部站點';
  if (selectedWorkcenterGroups.value.length === 1) return selectedWorkcenterGroups.value[0];
  return `已選 ${selectedWorkcenterGroups.value.length} 個站群組`;
});

// ---- Table columns ----
const TABLE_COLUMNS: { key: string; label: string }[] = [
  { key: 'CONTAINERNAME', label: 'LOT ID' },
  { key: 'PJ_WORKORDER', label: '工單' },
  { key: 'WORKCENTER_GROUP', label: '站群組' },
  { key: 'WORKCENTERNAME', label: '站點' },
  { key: 'MATERIALPARTNAME', label: '料號' },
  { key: 'MATERIALLOTNAME', label: '物料批號' },
  { key: 'VENDORLOTNUMBER', label: '供應商批號' },
  { key: 'QTYREQUIRED', label: '應領量' },
  { key: 'QTYCONSUMED', label: '實際消耗' },
  { key: 'EQUIPMENTNAME', label: '機台' },
  { key: 'TXNDATE', label: '交易日期' },
  { key: 'PRIMARY_CATEGORY', label: '主分類' },
  { key: 'SECONDARY_CATEGORY', label: '副分類' },
];

// ---- Mode switching ----
function switchQueryMode(mode: 'forward' | 'reverse') {
  if (queryMode.value === mode) return;
  queryMode.value = mode;
  clearAll();
}

function switchForwardInputType(type: 'lot' | 'workorder') {
  if (forwardInputType.value === type) return;
  forwardInputType.value = type;
  inputText.value = '';
  clearResults();
}

function clearAll() {
  inputText.value = '';
  clearResults();
}

function clearResults() {
  rows.value = [];
  pagination.value = { page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 0 };
  errorMessage.value = '';
  warningMessage.value = '';
  unresolvedWarning.value = '';
  currentQueryHash.value = null;
  pollingJobId.value = null;
  _stopPolling();
}

// ---- Async polling helpers (task 8.3) ----
function _stopPolling() {
  if (_pollingTimer !== null) {
    clearTimeout(_pollingTimer);
    _pollingTimer = null;
  }
}

function _startPolling(jobId: string, queryPage: number) {
  _pollingAttempts = 0;
  function poll() {
    if (pollingJobId.value !== jobId) return; // stale poll, discard
    _pollingAttempts++;
    if (_pollingAttempts > _POLL_MAX_ATTEMPTS) {
      loading.value = false;
      pollingJobId.value = null;
      errorMessage.value = '查詢逾時，請重試';
      return;
    }
    apiGet<MaterialTraceJobStatus>(`/api/material-trace/job/${jobId}`, { timeout: 10000 })
      .then((res) => {
        if (pollingJobId.value !== jobId) return;
        const jobData = res.success ? res.data : undefined;
        const status = String(jobData?.status || '').toLowerCase();
        if (status === 'completed') {
          pollingJobId.value = null;
          _stopPolling();
          void executePrimaryQuery(queryPage, { _fromPoll: true });
        } else if (status === 'failed') {
          loading.value = false;
          pollingJobId.value = null;
          errorMessage.value = jobData?.error || '查詢失敗，請稍後再試';
        } else {
          _pollingTimer = setTimeout(poll, _POLL_INTERVAL_MS);
        }
      })
      .catch(() => {
        if (pollingJobId.value === jobId) {
          _pollingTimer = setTimeout(poll, _POLL_INTERVAL_MS);
        }
      });
  }
  _pollingTimer = setTimeout(poll, _POLL_INTERVAL_MS);
}

// ---- Workcenter multi-select ----
function toggleWorkcenterGroup(group: string) {
  const idx = selectedWorkcenterGroups.value.indexOf(group);
  if (idx >= 0) {
    selectedWorkcenterGroups.value.splice(idx, 1);
  } else {
    selectedWorkcenterGroups.value.push(group);
  }
}

function selectAllWorkcenterGroups() {
  selectedWorkcenterGroups.value = [...workcenterGroupOptions.value];
}

function clearWorkcenterGroups() {
  selectedWorkcenterGroups.value = [];
}

// ---- API calls ----
async function loadFilterOptions() {
  try {
    const res = await apiGet<MaterialTraceFilterOptions>('/api/material-trace/filter-options', { timeout: API_TIMEOUT });
    if (res.success && res.data?.workcenter_groups) {
      workcenterGroupOptions.value = res.data.workcenter_groups;
    }
  } catch {
    // Silently ignore — filter options will be empty
  }
}

async function executePrimaryQuery(page: number = 1, opts: { paginationOnly?: boolean; _fromPoll?: boolean } = {}) {
  const { paginationOnly = false, _fromPoll = false } = opts;
  if (_fromPoll) {
    // loading is already true from the original call — proceed directly
  } else if (paginationOnly) {
    if (loading.value || paginationLoading.value) return;
  } else {
    if (!canQuery.value) return;
    _stopPolling();
    pollingJobId.value = null;
    currentQueryHash.value = null;
    errorMessage.value = '';
    warningMessage.value = '';
    unresolvedWarning.value = '';
    loading.value = true;
    paginationLoading.value = false;
  }

  if (paginationOnly) {
    paginationLoading.value = true;
  }

  const body: { mode: string; values: string[]; page: number; per_page: number; workcenter_groups?: string[] } = {
    mode: queryModeForApi.value,
    values: parsedValues.value,
    page,
    per_page: DEFAULT_PER_PAGE,
  };
  if (selectedWorkcenterGroups.value.length > 0) {
    body.workcenter_groups = selectedWorkcenterGroups.value;
  }

  try {
    const result = await apiPost<MaterialTraceQueryPayload>('/api/material-trace/query', body, { timeout: API_TIMEOUT });

    if (!result.success) {
      errorMessage.value = result.error?.message || '查詢失敗';
      if (!paginationOnly && !_fromPoll) {
        rows.value = [];
        pagination.value = { page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 0 };
      }
      return;
    }

    const payload = result.data || {};

    // ── Task 8.3: Handle async 202 response ────────────────────────────────
    if (payload.async) {
      pollingJobId.value = payload.job_id ?? null;
      currentQueryHash.value = payload.query_hash || null;
      _startPolling(payload.job_id as string, page);
      return; // loading stays true during polling
    }

    // Spool hit or sync result — capture query_hash if present
    currentQueryHash.value = payload.query_hash || null;

    rows.value = payload.rows || [];
    pagination.value = payload.pagination || {
      page: 1,
      per_page: DEFAULT_PER_PAGE,
      total: 0,
      total_pages: 0,
    };

    // Handle meta warnings
    if (payload.meta?.unresolved && payload.meta.unresolved.length > 0) {
      unresolvedWarning.value = `以下 LOT ID 無法解析：${payload.meta.unresolved.join('、')}`;
    }
    warningMessage.value = buildQualityWarning(payload.quality_meta, payload.meta);
  } catch (err) {
    errorMessage.value = (err instanceof Error ? err.message : null) || '查詢失敗，請稍後再試';
    if (!paginationOnly && !_fromPoll) {
      rows.value = [];
    }
  } finally {
    if (paginationOnly) {
      paginationLoading.value = false;
    } else if (!pollingJobId.value) {
      // Only clear loading if we're not waiting for a poll result
      loading.value = false;
    }
  }
}

function goToPage(page: number) {
  if (page < 1 || page > Number(pagination.value?.total_pages || 1)) return;
  void executePrimaryQuery(page, { paginationOnly: true });
}

function buildQualityWarning(qualityMeta?: QualityMeta | null, fallbackMeta?: QualityMeta | null): string {
  const status = String(qualityMeta?.status || '').toLowerCase();
  const maxRows = qualityMeta?.max_rows || fallbackMeta?.max_rows;
  if (!status || status === 'complete') {
    return '';
  }
  if (status === 'truncated') {
    const maxRowsText = Number(maxRows || 0).toLocaleString();
    return `查詢結果可能已截斷（上限 ${maxRowsText || '10,000'} 筆），請縮小查詢範圍`;
  }
  if (status === 'partial') {
    return '查詢結果為部分資料，請留意可能缺漏';
  }
  return '查詢結果完整性異常，請稍後重試或縮小查詢範圍';
}

async function exportCsv() {
  if (!canExport.value) return;

  const body: { mode: string; values: string[]; workcenter_groups?: string[]; query_hash?: string } = {
    mode: queryModeForApi.value,
    values: parsedValues.value,
  };
  if (selectedWorkcenterGroups.value.length > 0) {
    body.workcenter_groups = selectedWorkcenterGroups.value;
  }
  // Task 8.3: pass query_hash so backend can stream from DuckDB spool
  if (currentQueryHash.value) {
    body.query_hash = currentQueryHash.value;
  }

  try {
    const response = await fetch('/api/material-trace/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({})) as Record<string, unknown>;
      errorMessage.value = (data.error as Record<string, unknown> | undefined)?.message as string || '匯出失敗';
      return;
    }

    const exportStatus = String(response.headers.get('X-Query-Quality-Status') || '').toLowerCase();
    if (exportStatus && exportStatus !== 'complete') {
      warningMessage.value = buildQualityWarning(
        {
          status: exportStatus,
          max_rows: response.headers.get('X-Query-Quality-Max-Rows') || response.headers.get('X-Max-Rows'),
        },
        null,
      );
    } else if (String(response.headers.get('X-Truncated') || '').toLowerCase() === 'true') {
      warningMessage.value = '匯出結果可能已截斷，請縮小查詢範圍後重試';
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'material_trace.csv';
    a.click();
    URL.revokeObjectURL(url);
  } catch (err) {
    errorMessage.value = (err instanceof Error ? err.message : null) || '匯出失敗，請稍後再試';
  }
}

// ---- Lifecycle ----
onMounted(() => {
  loadFilterOptions();
});

onUnmounted(() => {
  _stopPolling();
});

// Close dropdown on click outside
function onDocumentClick(e: MouseEvent) {
  if (!(e.target as HTMLElement | null)?.closest('.multi-select')) {
    workcenterDropdownOpen.value = false;
  }
}
</script>

<template>
  <div class="dashboard theme-material-trace" @click="onDocumentClick">
    <PageHeader
      title="原物料追溯查詢"
      :show-refresh="false"
    />

    <!-- Error / Warning Banners -->
    <ErrorBanner :message="errorMessage" @dismiss="errorMessage = ''" />
    <div v-if="unresolvedWarning" class="warning-banner">{{ unresolvedWarning }}</div>
    <div v-if="warningMessage" class="warning-banner">{{ warningMessage }}</div>

    <!-- Query Card -->
    <div class="card ui-card">
      <div class="card-header ui-card-header">
        <span class="card-title ui-card-title">查詢條件</span>
      </div>
      <div class="card-body ui-card-body">
        <!-- Mode tabs -->
        <div class="mode-tab-row mode-tab-row--spaced">
          <button
            class="mode-tab"
            :class="{ active: queryMode === 'forward' }"
            @click="switchQueryMode('forward')"
          >
            正向查詢：LOT/工單 → 原物料
          </button>
          <button
            class="mode-tab"
            :class="{ active: queryMode === 'reverse' }"
            @click="switchQueryMode('reverse')"
          >
            反向查詢：原物料 → LOT
          </button>
        </div>

        <div class="filter-panel">
          <!-- Forward: input type selector -->
          <div v-if="queryMode === 'forward'" class="filter-group">
            <label class="filter-label">輸入類型</label>
            <div class="input-type-row">
              <select
                class="filter-input input-type-select"
                :value="forwardInputType"
                @change="switchForwardInputType(($event.target as HTMLSelectElement).value as 'lot' | 'workorder')"
              >
                <option value="lot">LOT ID</option>
                <option value="workorder">工單</option>
              </select>
            </div>
          </div>

          <!-- Workcenter group filter -->
          <div class="filter-group">
            <label class="filter-label">站群組篩選</label>
            <div class="multi-select" @click.stop>
              <button
                class="multi-select-trigger"
                @click="workcenterDropdownOpen = !workcenterDropdownOpen"
              >
                <span class="multi-select-text">{{ workcenterTriggerText }}</span>
                <span class="multi-select-arrow">&#9662;</span>
              </button>
              <div v-if="workcenterDropdownOpen" class="multi-select-dropdown">
                <input
                  v-model="workcenterSearch"
                  class="multi-select-search"
                  placeholder="搜尋站群組..."
                />
                <div class="multi-select-options">
                  <button
                    v-for="group in filteredWorkcenterOptions"
                    :key="group"
                    class="multi-select-option"
                    @click="toggleWorkcenterGroup(group)"
                  >
                    <input
                      type="checkbox"
                      :checked="selectedWorkcenterGroups.includes(group)"
                      tabindex="-1"
                    />
                    {{ group }}
                  </button>
                  <div v-if="filteredWorkcenterOptions.length === 0" class="multi-select-empty">
                    無符合的站群組
                  </div>
                </div>
                <div class="multi-select-actions">
                  <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="selectAllWorkcenterGroups">全選</button>
                  <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="clearWorkcenterGroups">清除</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Textarea input -->
          <div class="filter-group filter-group-full">
            <label class="filter-label">
              {{
                queryMode === 'forward'
                  ? forwardInputType === 'lot'
                    ? 'LOT ID（每行一筆或逗號分隔，支援萬用字元 * ）'
                    : '工單號碼（每行一筆或逗號分隔，支援萬用字元 * ）'
                  : '原物料批號（每行一筆或逗號分隔，支援萬用字元 * ）'
              }}
            </label>
            <textarea
              v-model="inputText"
              class="filter-input filter-textarea"
              rows="5"
              :placeholder="
                queryMode === 'forward'
                  ? forwardInputType === 'lot'
                    ? 'GA25060001-A01\nGA250605*\n...'
                    : 'WO-2025-001\nWO-2025*\n...'
                  : 'WIRE-LOT-20250101-A\nSLD-LOT-2025*\n...'
              "
            ></textarea>
            <div class="input-count" :class="{ 'over-limit': isOverLimit }">
              已輸入 {{ inputCount }} 筆
              <template v-if="isOverLimit">
                （超過上限 {{ currentInputLimit }} 筆）
              </template>
            </div>
          </div>

          <!-- Buttons -->
          <div class="filter-toolbar">
            <div class="filter-actions">
              <button
                class="ui-btn ui-btn--primary"
                :class="{ 'is-loading': loading }"
                :disabled="!canQuery || loading"
                @click="executePrimaryQuery()"
              >
                <LoadingSpinner v-if="loading" size="sm" />
                {{ loading ? '查詢中...' : '查詢' }}
              </button>
              <button class="ui-btn ui-btn--secondary" @click="clearAll">清除</button>
              <button class="ui-btn ui-btn--secondary" :disabled="!canExport" @click="exportCsv">
                匯出 CSV
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Result Card -->
    <div v-if="hasResults || loading || paginationLoading" class="card ui-card">
      <div class="card-header ui-card-header">
        <span class="card-title ui-card-title">
          查詢結果
          <template v-if="pagination.total > 0">
            （共 {{ pagination.total.toLocaleString() }} 筆）
          </template>
        </span>
      </div>
      <div class="card-body ui-card-body result-card-body">
        <DataTable
          :data="rows"
          :loading="loading || paginationLoading"
          :pagination="pagination.total_pages > 1 ? { page: pagination.page, totalPages: pagination.total_pages, infoText: `第 ${pagination.page} / ${pagination.total_pages} 頁，共 ${pagination.total.toLocaleString()} 筆` } : null"
          @page-change="goToPage"
        >
          <DataTableColumn v-for="col in TABLE_COLUMNS" :key="col.key" :column-key="col.key" :label="col.label" :sortable="true" />
        </DataTable>
      </div>
    </div>
  </div>
</template>
