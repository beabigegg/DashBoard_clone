<script setup>
import { computed, onMounted, reactive, ref } from 'vue';

import { apiGet, apiPost } from '../core/api.js';
import MultiSelect from '../resource-shared/components/MultiSelect.vue';
import { navigateToRuntimeRoute, replaceRuntimeHistory } from '../core/shell-navigation.js';
import { buildDrilldownNotice, toQueryParams } from './utils.js';

const API_TIMEOUT = 90000;
const DEFAULT_PER_PAGE = 50;
const DEFAULT_WORKCENTER_GROUP_OPTIONS = [
  '焊接_DB',
  '焊接_WB',
  '成型',
  '去膠',
  '水吹砂',
  '電鍍',
  '移印',
  '切彎腳',
  'TMTT',
  '品檢',
  'FQC',
];

const loading = ref(false);
const trendLoading = ref(false);
const summaryLoading = ref(false);
const alertLoading = ref(false);
const drilldownLoadingKey = ref('');

const errorMessage = ref('');
const warningMessage = ref('');
const linkageWarning = ref('');

const queryId = ref('');
const hasQueried = ref(false);
const committedDateRange = reactive({
  start_date: '',
  end_date: '',
});

const summary = ref({ transaction_qty: 0, scrap_qty: 0, yield_pct: 100 });
const trend = ref([]);
const alerts = ref([]);
const pagination = ref({ page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 1 });
const sortState = reactive({ sort_by: 'date_bucket', sort_dir: 'desc' });
const workcenterGroupOptions = ref([...DEFAULT_WORKCENTER_GROUP_OPTIONS]);
const lineOptions = ref([]);
const packageOptions = ref([]);
const typeOptions = ref([]);
const functionOptions = ref([]);
const operationOptions = ref([]);

const filters = reactive({
  start_date: '',
  end_date: '',
  workcenterGroups: [],
  lines: [],
  packages: [],
  types: [],
  functions: [],
  operations: [],
  risk_threshold: '98',
  min_scrap_qty: '1',
});

const pageTitle = 'Yield Alert Center';

const parsedFilters = computed(() => ({
  start_date: filters.start_date,
  end_date: filters.end_date,
  workcenter_groups: filters.workcenterGroups,
  lines: filters.lines,
  packages: filters.packages,
  types: filters.types,
  functions: filters.functions,
  operations: filters.operations,
  risk_threshold: filters.risk_threshold,
  min_scrap_qty: filters.min_scrap_qty,
}));

const canSubmit = computed(() => !loading.value && Boolean(filters.start_date && filters.end_date));
const canApplySupplementary = computed(() => !loading.value && Boolean(queryId.value) && canSubmit.value);
const isDateStageDirty = computed(() => (
  !queryId.value
  || filters.start_date !== committedDateRange.start_date
  || filters.end_date !== committedDateRange.end_date
));
const submitLabel = computed(() => (isDateStageDirty.value ? '查詢(日期)' : '套用篩選'));
const hasData = computed(() => alerts.value.length > 0);
const alertEmptyMessage = computed(() => {
  if (!hasQueried.value) return '請先設定日期並查詢';
  if (alertLoading.value) return '告警資料載入中...';
  return '目前無符合條件的告警候選';
});
const trendEmptyMessage = computed(() => {
  if (!hasQueried.value) return '請先設定日期並查詢';
  return '尚無趨勢資料';
});

const summaryCards = computed(() => [
  {
    key: 'transaction',
    label: '移轉量',
    value: Number(summary.value.transaction_qty || 0).toLocaleString(),
    tone: 'base',
  },
  {
    key: 'scrap',
    label: '報廢量',
    value: Number(summary.value.scrap_qty || 0).toLocaleString(),
    tone: 'warn',
  },
  {
    key: 'yield',
    label: '良率',
    value: `${Number(summary.value.yield_pct || 0).toFixed(2)}%`,
    tone: Number(summary.value.yield_pct || 0) < Number(filters.risk_threshold || 98) ? 'danger' : 'good',
  },
]);

const linePoints = computed(() => {
  if (!trend.value.length) {
    return '';
  }
  const w = 640;
  const h = 140;
  const values = trend.value.map((item) => Number(item.yield_pct || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.0001);
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * w;
      const y = h - ((value - min) / span) * h;
      return `${x},${y}`;
    })
    .join(' ');
});

function setDefaultDateRange() {
  const end = new Date();
  const start = new Date(Date.now() - 29 * 24 * 60 * 60 * 1000);
  filters.start_date = start.toISOString().slice(0, 10);
  filters.end_date = end.toISOString().slice(0, 10);
}

function syncUrlState() {
  const params = toQueryParams({
    query_id: queryId.value,
    start_date: parsedFilters.value.start_date,
    end_date: parsedFilters.value.end_date,
    workcenter_groups: parsedFilters.value.workcenter_groups,
    lines: parsedFilters.value.lines,
    packages: parsedFilters.value.packages,
    types: parsedFilters.value.types,
    functions: parsedFilters.value.functions,
    operations: parsedFilters.value.operations,
    risk_threshold: parsedFilters.value.risk_threshold,
    min_scrap_qty: parsedFilters.value.min_scrap_qty,
    page: pagination.value.page,
    per_page: pagination.value.per_page,
    sort_by: sortState.sort_by,
    sort_dir: sortState.sort_dir,
  });
  replaceRuntimeHistory(`/yield-alert-center?${params.toString()}`);
}

function readArrayParam(params, key) {
  const values = params.getAll(key).map((item) => String(item || '').trim()).filter(Boolean);
  if (values.length > 0) {
    return values;
  }
  return String(params.get(key) || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function restoreFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const restoredQueryId = String(params.get('query_id') || '').trim();
  if (restoredQueryId) {
    queryId.value = restoredQueryId;
  }
  const startDate = String(params.get('start_date') || '').trim();
  const endDate = String(params.get('end_date') || '').trim();
  if (startDate) filters.start_date = startDate;
  if (endDate) filters.end_date = endDate;
  if (queryId.value && filters.start_date && filters.end_date) {
    committedDateRange.start_date = filters.start_date;
    committedDateRange.end_date = filters.end_date;
  }

  const groupsFromUrl = readArrayParam(params, 'workcenter_groups');
  const groupsFromLegacy = readArrayParam(params, 'departments');
  filters.workcenterGroups = groupsFromUrl.length > 0 ? groupsFromUrl : groupsFromLegacy;
  filters.lines = readArrayParam(params, 'lines');
  filters.packages = readArrayParam(params, 'packages');
  filters.types = readArrayParam(params, 'types');
  filters.functions = readArrayParam(params, 'functions');
  filters.operations = readArrayParam(params, 'operations');

  const riskThreshold = String(params.get('risk_threshold') || '').trim();
  const minScrapQty = String(params.get('min_scrap_qty') || '').trim();
  if (riskThreshold) filters.risk_threshold = riskThreshold;
  if (minScrapQty) filters.min_scrap_qty = minScrapQty;

  const page = Number(params.get('page') || '1');
  if (Number.isFinite(page) && page > 0) {
    pagination.value.page = page;
  }
  const perPage = Number(params.get('per_page') || String(DEFAULT_PER_PAGE));
  if (Number.isFinite(perPage) && perPage > 0) {
    pagination.value.per_page = perPage;
  }

  const sortBy = String(params.get('sort_by') || '').trim();
  const sortDir = String(params.get('sort_dir') || '').trim().toLowerCase();
  if (sortBy) sortState.sort_by = sortBy;
  if (sortDir === 'asc' || sortDir === 'desc') sortState.sort_dir = sortDir;
}

async function loadFilterOptions() {
  try {
    const resp = await apiGet('/api/yield-alert/filter-options', { timeout: 30000 });
    if (!resp.success) {
      return;
    }
    const options = Array.isArray(resp.data?.workcenter_groups)
      ? resp.data.workcenter_groups.map((item) => String(item || '').trim()).filter(Boolean)
      : [];
    if (options.length > 0) {
      workcenterGroupOptions.value = options;
    }
  } catch (_error) {
    // Keep local fallback options when backend options are unavailable.
  }
}

function isCacheExpiredError(error) {
  const payloadError = String(error?.payload?.error || '').trim();
  const message = String(error?.message || '').trim();
  return payloadError === 'cache_expired' || message === 'cache_expired' || Number(error?.status || 0) === 410;
}

async function executePrimaryQuery() {
  const resp = await apiPost('/api/yield-alert/query', {
    start_date: filters.start_date,
    end_date: filters.end_date,
  }, {
    timeout: API_TIMEOUT,
  });
  if (!resp.success || !resp.query_id) {
    throw new Error(resp.error || '主查詢執行失敗');
  }
  queryId.value = String(resp.query_id);
  committedDateRange.start_date = filters.start_date;
  committedDateRange.end_date = filters.end_date;
}

async function loadCachedView(page = 1) {
  if (!queryId.value) {
    throw new Error('尚未建立日期查詢快取');
  }

  summaryLoading.value = true;
  trendLoading.value = true;
  alertLoading.value = true;

  const resp = await apiGet('/api/yield-alert/view', {
    params: {
      query_id: queryId.value,
      workcenter_groups: parsedFilters.value.workcenter_groups,
      lines: parsedFilters.value.lines,
      packages: parsedFilters.value.packages,
      types: parsedFilters.value.types,
      functions: parsedFilters.value.functions,
      operations: parsedFilters.value.operations,
      risk_threshold: parsedFilters.value.risk_threshold,
      min_scrap_qty: parsedFilters.value.min_scrap_qty,
      page,
      per_page: pagination.value.per_page,
      sort_by: sortState.sort_by,
      sort_dir: sortState.sort_dir,
    },
    timeout: API_TIMEOUT,
  });

  if (!resp.success) {
    throw new Error(resp.error || '視圖查詢失敗');
  }

  summary.value = resp.data?.summary || summary.value;
  trend.value = resp.data?.trend?.items || [];
  alerts.value = resp.data?.alerts?.items || [];
  pagination.value = resp.data?.alerts?.pagination || pagination.value;

  const fo = resp.data?.filter_options || {};
  if (fo.lines?.length) lineOptions.value = fo.lines;
  if (fo.packages?.length) packageOptions.value = fo.packages;
  if (fo.types?.length) typeOptions.value = fo.types;
  if (fo.functions?.length) functionOptions.value = fo.functions;
  if (fo.operations?.length) operationOptions.value = fo.operations;

  const quality = resp.data?.alerts?.quality || {};
  linkageWarning.value = quality.warning
    ? `映射未匹配比例偏高 (${Number(quality.unmatched_ratio || 0) * 100}%)，請留意資料完整性`
    : '';
}

async function runQuery(page = 1) {
  if (!canSubmit.value) {
    return;
  }

  loading.value = true;
  errorMessage.value = '';
  warningMessage.value = '';
  linkageWarning.value = '';

  try {
    if (isDateStageDirty.value) {
      await executePrimaryQuery();
    }
    try {
      await loadCachedView(page);
    } catch (error) {
      if (!isDateStageDirty.value && isCacheExpiredError(error)) {
        await executePrimaryQuery();
        await loadCachedView(page);
      } else {
        throw error;
      }
    }
    hasQueried.value = true;
    syncUrlState();
  } catch (error) {
    errorMessage.value = error.message || '查詢失敗，請稍後再試';
  } finally {
    loading.value = false;
    summaryLoading.value = false;
    trendLoading.value = false;
    alertLoading.value = false;
  }
}

function onSort(field) {
  if (!hasQueried.value) {
    return;
  }
  if (sortState.sort_by === field) {
    sortState.sort_dir = sortState.sort_dir === 'asc' ? 'desc' : 'asc';
  } else {
    sortState.sort_by = field;
    sortState.sort_dir = field === 'date_bucket' ? 'desc' : 'asc';
  }
  runQuery(1);
}

function riskClass(level) {
  if (level === 'high') return 'risk-high';
  if (level === 'medium') return 'risk-medium';
  return 'risk-low';
}

async function openDrilldown(row) {
  const key = `${row.date_bucket}|${row.workorder}|${row.reason_code}`;
  if (drilldownLoadingKey.value) {
    return;
  }
  drilldownLoadingKey.value = key;
  warningMessage.value = '';
  try {
    const resp = await apiGet('/api/yield-alert/drilldown-context', {
      params: {
        date_bucket: row.date_bucket,
        workorder: row.workorder,
        reason_code: row.reason_code,
      },
      timeout: API_TIMEOUT,
    });
    if (!resp.success || !resp.data?.launch_href) {
      throw new Error(resp.error || '建立追溯連結失敗');
    }

    const notice = buildDrilldownNotice(resp.data.match_status, resp.data.fallback_reason);
    if (notice) {
      warningMessage.value = notice;
    }
    navigateToRuntimeRoute(resp.data.launch_href);
  } catch (error) {
    errorMessage.value = error.message || '開啟追溯頁面失敗';
  } finally {
    drilldownLoadingKey.value = '';
  }
}

function resetFilters() {
  queryId.value = '';
  hasQueried.value = false;
  committedDateRange.start_date = '';
  committedDateRange.end_date = '';
  filters.workcenterGroups = [];
  filters.lines = [];
  filters.packages = [];
  filters.types = [];
  filters.functions = [];
  filters.operations = [];
  filters.risk_threshold = '98';
  filters.min_scrap_qty = '1';
  setDefaultDateRange();
  summary.value = { transaction_qty: 0, scrap_qty: 0, yield_pct: 100 };
  trend.value = [];
  alerts.value = [];
  pagination.value = { page: 1, per_page: DEFAULT_PER_PAGE, total: 0, total_pages: 1 };
  linkageWarning.value = '';
  warningMessage.value = '';
  errorMessage.value = '';
  syncUrlState();
}

onMounted(() => {
  setDefaultDateRange();
  restoreFromUrl();
  loadFilterOptions();
  if (filters.start_date && filters.end_date) {
    // Always start via primary-query path on mount.
    // If dataset cache is still valid the backend returns instantly (no Oracle re-query).
    // If cache has expired the backend rebuilds it before we call loadCachedView,
    // avoiding the cross-worker race where loadCachedView sees a miss right after
    // executePrimaryQuery stored to a different process-level cache slot.
    queryId.value = '';
    committedDateRange.start_date = '';
    committedDateRange.end_date = '';
    runQuery(pagination.value.page || 1);
  }
});
</script>

<template>
  <div class="yield-alert-page">
    <div class="ya-header">
      <div class="ya-header-left">
        <h1>{{ pageTitle }}</h1>
        <p>以 ERP WIP 移轉/報廢資料快速定位良率風險，並回鑽報廢歷史</p>
      </div>
    </div>

    <section class="filter-panel primary-query-panel">
      <header class="panel-header">
        <h2>第一階段：日期主查詢</h2>
        <span>{{ queryId ? `已建立快取: ${queryId}` : '尚未查詢' }}</span>
      </header>
      <div class="filter-row two">
        <label>
          開始日期
          <input v-model="filters.start_date" class="text-input" type="date" />
        </label>
        <label>
          結束日期
          <input v-model="filters.end_date" class="text-input" type="date" />
        </label>
      </div>
      <div class="filter-row one">
        <div class="filter-actions">
          <button class="btn btn-primary" :disabled="!canSubmit" @click="runQuery(1)">
            {{ isDateStageDirty ? '執行日期查詢' : '重新查詢日期範圍' }}
          </button>
          <button class="btn btn-secondary" :disabled="loading" @click="resetFilters">清除條件</button>
        </div>
      </div>
    </section>

    <section class="filter-panel supplementary-query-panel">
      <header class="panel-header">
        <h2>第二階段：補充篩選 (快取內計算)</h2>
        <span>不重新查 Oracle</span>
      </header>
      <template v-if="queryId">
        <div class="filter-row three">
          <label>
            站別群組(可多選)
            <MultiSelect
              v-model="filters.workcenterGroups"
              :options="workcenterGroupOptions"
              placeholder="請選擇站別群組 (焊接_DW 已併入 焊接_WB)"
              :searchable="true"
            />
          </label>
          <label v-if="lineOptions.length > 0">
            Line
            <MultiSelect
              v-model="filters.lines"
              :options="lineOptions"
              placeholder="請選擇 Line"
              :searchable="true"
            />
          </label>
          <label v-if="packageOptions.length > 0">
            Package
            <MultiSelect
              v-model="filters.packages"
              :options="packageOptions"
              placeholder="請選擇 Package"
              :searchable="true"
            />
          </label>
        </div>
        <div v-if="typeOptions.length > 0 || functionOptions.length > 0 || operationOptions.length > 0" class="filter-row three">
          <label v-if="typeOptions.length > 0">
            Type
            <MultiSelect
              v-model="filters.types"
              :options="typeOptions"
              placeholder="請選擇 Type"
              :searchable="true"
            />
          </label>
          <label v-if="functionOptions.length > 0">
            Function
            <MultiSelect
              v-model="filters.functions"
              :options="functionOptions"
              placeholder="請選擇 Function"
              :searchable="true"
            />
          </label>
          <label v-if="operationOptions.length > 0">
            Operation
            <MultiSelect
              v-model="filters.operations"
              :options="operationOptions"
              placeholder="請選擇 Operation"
              :searchable="true"
            />
          </label>
        </div>
        <div class="filter-row three">
          <label>
            風險門檻良率(%)
            <input v-model="filters.risk_threshold" class="text-input" type="number" step="0.1" min="0" max="100" />
          </label>
          <label>
            最小報廢量
            <input v-model="filters.min_scrap_qty" class="text-input" type="number" step="0.1" min="0" />
          </label>
          <div class="filter-actions">
            <button class="btn btn-primary" :disabled="!canApplySupplementary" @click="runQuery(1)">
              {{ submitLabel }}
            </button>
          </div>
        </div>
      </template>
      <p v-else class="empty-note">請先在第一階段執行日期查詢，才能套用補充篩選。</p>
    </section>

    <section class="status-stack">
      <div v-if="errorMessage" class="status error">{{ errorMessage }}</div>
      <div v-if="warningMessage" class="status warn">{{ warningMessage }}</div>
      <div v-if="linkageWarning" class="status warn">{{ linkageWarning }}</div>
    </section>

    <section class="summary-grid">
      <article v-for="card in summaryCards" :key="card.key" class="summary-card" :class="`tone-${card.tone}`">
        <h3>{{ card.label }}</h3>
        <p>{{ card.value }}</p>
      </article>
    </section>

    <section class="trend-panel">
      <header>
        <h2>良率趨勢 (日)</h2>
        <span v-if="trendLoading">載入中...</span>
      </header>
      <div v-if="trend.length > 1" class="trend-chart">
        <svg viewBox="0 0 640 160" role="img" aria-label="yield trend line chart">
          <polyline :points="linePoints" fill="none" stroke="#2563eb" stroke-width="3" />
        </svg>
      </div>
      <p v-else class="empty-note">{{ trendEmptyMessage }}</p>
      <div class="trend-table-wrap" v-if="trend.length > 0">
        <table class="trend-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>移轉量</th>
              <th>報廢量</th>
              <th>良率(%)</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in trend" :key="row.date_bucket">
              <td>{{ row.date_bucket }}</td>
              <td>{{ Number(row.transaction_qty || 0).toLocaleString() }}</td>
              <td>{{ Number(row.scrap_qty || 0).toLocaleString() }}</td>
              <td>{{ Number(row.yield_pct || 0).toFixed(2) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="alerts-panel">
      <header>
        <h2>告警候選清單</h2>
        <span>{{ pagination.total }} 筆</span>
      </header>
      <div class="table-wrap" v-if="hasData">
        <table class="alert-table">
          <thead>
            <tr>
              <th><button class="th-btn" @click="onSort('date_bucket')">日期</button></th>
              <th><button class="th-btn" @click="onSort('workorder')">工單</button></th>
              <th>原因碼</th>
              <th>站別群組</th>
              <th><button class="th-btn" @click="onSort('scrap_qty')">報廢量</button></th>
              <th><button class="th-btn" @click="onSort('yield_pct')">良率(%)</button></th>
              <th><button class="th-btn" @click="onSort('risk_score')">風險分數</button></th>
              <th>映射狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in alerts" :key="`${row.date_bucket}-${row.workorder}-${row.reason_code}-${row.department}`">
              <td>{{ row.date_bucket }}</td>
              <td>{{ row.workorder }}</td>
              <td>{{ row.reason_code }}</td>
              <td>{{ row.department }}</td>
              <td>{{ Number(row.scrap_qty || 0).toLocaleString() }}</td>
              <td>{{ Number(row.yield_pct || 0).toFixed(2) }}</td>
              <td>
                <span class="risk-pill" :class="riskClass(row.risk_level)">
                  {{ row.risk_level }} · {{ Number(row.risk_score || 0).toFixed(2) }}
                </span>
              </td>
              <td>
                <span class="match-pill" :class="`match-${row.match_status}`">{{ row.match_status }}</span>
              </td>
              <td>
                <button
                  class="btn btn-mini"
                  :disabled="Boolean(drilldownLoadingKey)"
                  @click="openDrilldown(row)"
                >
                  {{ drilldownLoadingKey === `${row.date_bucket}|${row.workorder}|${row.reason_code}` ? '開啟中...' : '查看追溯' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="empty-note">{{ alertEmptyMessage }}</p>

      <footer class="pagination">
        <button class="btn btn-secondary" :disabled="loading || pagination.page <= 1" @click="runQuery(pagination.page - 1)">上一頁</button>
        <span>第 {{ pagination.page }} / {{ pagination.total_pages }} 頁</span>
        <button class="btn btn-secondary" :disabled="loading || pagination.page >= pagination.total_pages" @click="runQuery(pagination.page + 1)">下一頁</button>
      </footer>
    </section>
  </div>
</template>
