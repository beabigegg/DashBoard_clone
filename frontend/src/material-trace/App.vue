<script setup>
import { computed, onMounted, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import { parseMultiLineInput } from '../core/reject-history-filters.js';

const API_TIMEOUT = 60000;
const DEFAULT_PER_PAGE = 20;
const FORWARD_INPUT_LIMIT = 200;
const REVERSE_INPUT_LIMIT = 50;

// ---- Query mode state ----
const queryMode = ref('forward'); // 'forward' | 'reverse'
const forwardInputType = ref('lot'); // 'lot' | 'workorder'
const inputText = ref('');

// ---- Filter state ----
const workcenterGroupOptions = ref([]);
const selectedWorkcenterGroups = ref([]);
const workcenterDropdownOpen = ref(false);
const workcenterSearch = ref('');

// ---- Result state ----
const rows = ref([]);
const pagination = ref({ page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 0 });
const loading = ref(false);
const paginationLoading = ref(false);
const errorMessage = ref('');
const warningMessage = ref('');
const unresolvedWarning = ref('');

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
const TABLE_COLUMNS = [
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
function switchQueryMode(mode) {
  if (queryMode.value === mode) return;
  queryMode.value = mode;
  clearAll();
}

function switchForwardInputType(type) {
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
}

// ---- Workcenter multi-select ----
function toggleWorkcenterGroup(group) {
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
    const res = await apiGet('/api/material-trace/filter-options', { timeout: API_TIMEOUT });
    if (res.success && res.data?.workcenter_groups) {
      workcenterGroupOptions.value = res.data.workcenter_groups;
    }
  } catch {
    // Silently ignore — filter options will be empty
  }
}

async function executePrimaryQuery(page = 1, { paginationOnly = false } = {}) {
  if (paginationOnly) {
    if (loading.value || paginationLoading.value) return;
  } else if (!canQuery.value) {
    return;
  }

  if (!paginationOnly) {
    errorMessage.value = '';
    warningMessage.value = '';
    unresolvedWarning.value = '';
    loading.value = true;
    paginationLoading.value = false;
  } else {
    paginationLoading.value = true;
  }

  const body = {
    mode: queryModeForApi.value,
    values: parsedValues.value,
    page,
    per_page: DEFAULT_PER_PAGE,
  };
  if (selectedWorkcenterGroups.value.length > 0) {
    body.workcenter_groups = selectedWorkcenterGroups.value;
  }

  try {
    const result = await apiPost('/api/material-trace/query', body, { timeout: API_TIMEOUT });

    if (!result.success) {
      errorMessage.value = result.error?.message || '查詢失敗';
      if (!paginationOnly) {
        rows.value = [];
        pagination.value = { page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 0 };
      }
      return;
    }

    const payload = result.data || {};
    rows.value = payload.rows || [];
    pagination.value = payload.pagination || {
      page: 1,
      per_page: DEFAULT_PER_PAGE,
      total: 0,
      total_pages: 0,
    };

    // Handle meta warnings
    if (payload.meta?.unresolved?.length > 0) {
      unresolvedWarning.value = `以下 LOT ID 無法解析：${payload.meta.unresolved.join('、')}`;
    }
    warningMessage.value = buildQualityWarning(payload.quality_meta, payload.meta);
  } catch (err) {
    errorMessage.value = err.message || '查詢失敗，請稍後再試';
    if (!paginationOnly) {
      rows.value = [];
    }
  } finally {
    if (paginationOnly) {
      paginationLoading.value = false;
    } else {
      loading.value = false;
    }
  }
}

function goToPage(page) {
  if (page < 1 || page > Number(pagination.value?.total_pages || 1)) return;
  void executePrimaryQuery(page, { paginationOnly: true });
}

function buildQualityWarning(qualityMeta, fallbackMeta = null) {
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

  const body = {
    mode: queryModeForApi.value,
    values: parsedValues.value,
  };
  if (selectedWorkcenterGroups.value.length > 0) {
    body.workcenter_groups = selectedWorkcenterGroups.value;
  }

  try {
    const response = await fetch('/api/material-trace/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      errorMessage.value = data.error?.message || '匯出失敗';
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
    errorMessage.value = err.message || '匯出失敗，請稍後再試';
  }
}

// ---- Lifecycle ----
onMounted(() => {
  loadFilterOptions();
});

// Close dropdown on click outside
function onDocumentClick(e) {
  if (!e.target.closest('.multi-select')) {
    workcenterDropdownOpen.value = false;
  }
}
</script>

<template>
  <div class="dashboard theme-material-trace" @click="onDocumentClick">
    <!-- Header -->
    <div class="header material-trace-header">
      <div class="header-left">
        <h1>原物料追溯查詢</h1>
      </div>
    </div>

    <!-- Error / Warning Banners -->
    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>
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
                @change="switchForwardInputType($event.target.value)"
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
              <button class="ui-btn ui-btn--primary" :disabled="!canQuery" @click="executePrimaryQuery()">
                <span v-if="loading" class="btn-spinner"></span>
                查詢
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
      <div class="card-body ui-card-body">
        <!-- Loading overlay -->
        <div class="detail-table-wrap" :class="{ 'is-loading': loading, 'is-paginating': paginationLoading }">
          <div v-if="loading" class="table-loading-overlay">
            <span class="table-spinner"></span>
          </div>
          <table class="detail-table">
            <thead>
              <tr>
                <th v-for="col in TABLE_COLUMNS" :key="col.key">{{ col.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in rows" :key="idx">
                <td v-for="col in TABLE_COLUMNS" :key="col.key">{{ row[col.key] ?? '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Empty message -->
        <div v-if="!loading && !paginationLoading && rows.length === 0 && pagination.total === 0" class="empty-message">
          查無資料
        </div>

        <!-- Pagination -->
        <div v-if="pagination.total_pages > 1" class="pagination-bar">
          <div class="pagination-info">
            第 {{ pagination.page }} / {{ pagination.total_pages }} 頁，共
            {{ pagination.total.toLocaleString() }} 筆
          </div>
          <div class="pagination-actions">
            <button :disabled="loading || paginationLoading || pagination.page <= 1" @click="goToPage(pagination.page - 1)">
              上一頁
            </button>
            <button
              :disabled="loading || paginationLoading || pagination.page >= pagination.total_pages"
              @click="goToPage(pagination.page + 1)"
            >
              下一頁
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
