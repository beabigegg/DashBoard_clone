<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import { apiPost, apiGet } from '../core/api';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling';

import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';

import FilterBar from './FilterBar.vue';
import FineFilterBar from './FineFilterBar.vue';
import SummaryCards from './SummaryCards.vue';
import ParetoChart from './ParetoChart.vue';
import TrendChart from './TrendChart.vue';
import DetailTable from './DetailTable.vue';

import { useEapAlarmFilter } from './composables/useEapAlarmFilter';
import { useEapAlarmViews } from './composables/useEapAlarmViews';

// ── Resource filter options (from /api/resource/status/options) ──────────────
const resourceOptions = reactive({
  families: [] as string[],
  resources: [] as Array<{ id: string; name: string; family: string; workcenterGroup: string }>,
});

async function loadResourceOptions(): Promise<void> {
  try {
    const result = await apiGet('/api/resource/status/options', { timeout: 30000 });
    const data = (result as Record<string, unknown>)?.data as Record<string, unknown> | undefined;
    if (!data) return;
    resourceOptions.families = Array.isArray(data.families) ? (data.families as string[]) : [];
    resourceOptions.resources = Array.isArray(data.resources)
      ? (data.resources as typeof resourceOptions.resources)
      : [];
  } catch {
    // non-fatal: filter stays empty
  }
}

// ── Composables ────────────────────────────────────────────────────────────────
const {
  coarseFilter,
  fineFilter,
  filterOptions,
  queryId,
  spoolReady,
  setQueryId,
  resetFineFilter,
  resetFilterOptions,
  applyFilterOptions,
  buildFineFilterParams,
  setDefaultDateRange,
} = useEapAlarmFilter();

const {
  loading: viewLoading,
  error: viewError,
  summary,
  pareto,
  trend,
  trendGranularity,
  detail,
  detailPage,
  detailPerPage,
  resetAll: resetViews,
  fetchFilterOptions,
  fetchAllViews,
  fetchTrend,
  fetchDetail,
} = useEapAlarmViews();

// ── Async job progress ────────────────────────────────────────────────────────
const jobProgress = reactive({
  active: false,
  jobId: null as string | null,
  status: null as string | null,
  progress: '',
  pct: 0,
  elapsedSeconds: 0,
});
let _jobAbortController: AbortController | null = null;

// ── Loading / error state ────────────────────────────────────────────────────
const queryLoading = ref(false);
const errorMessage = ref('');

const hasNoResults = computed(
  () =>
    spoolReady.value &&
    queryId.value &&
    !viewLoading.summary &&
    summary.total_alarm_count === 0,
);

// ── Initial mount ─────────────────────────────────────────────────────────────
onMounted(() => {
  setDefaultDateRange();
  loadResourceOptions();
});

// ── Fine filter watcher: re-fetch views on change ────────────────────────────
watch(
  () => [fineFilter.alarm_text, fineFilter.eqp_id],
  async () => {
    if (!queryId.value) return;
    const params = buildFineFilterParams();
    await fetchAllViews(queryId.value, params);
  },
  { deep: true },
);

// ── Coarse filter submit (async spool) ────────────────────────────────────────
function cancelAsyncJob(): void {
  if (_jobAbortController) {
    _jobAbortController.abort();
    _jobAbortController = null;
  }
  jobProgress.active = false;
}

function validateCoarseFilter(): string {
  if (!coarseFilter.date_from) return '請填入開始日期';
  if (!coarseFilter.date_to) return '請填入結束日期';
  if (coarseFilter.date_from > coarseFilter.date_to) return '開始日期不能晚於結束日期';
  if (coarseFilter.machines.length === 0) return '請至少選擇一台機台（或先透過型號篩選再查詢）';
  return '';
}

async function handleSubmit(): Promise<void> {
  const validationError = validateCoarseFilter();
  if (validationError) {
    errorMessage.value = validationError;
    return;
  }

  // Cancel any in-flight job before new query
  cancelAsyncJob();

  // Reset view state
  errorMessage.value = '';
  queryLoading.value = true;
  queryId.value = '';
  spoolReady.value = false;
  resetFineFilter();
  resetFilterOptions();
  resetViews();

  try {
    const body = {
      date_from: coarseFilter.date_from,
      date_to: coarseFilter.date_to,
      machines: coarseFilter.machines,
    };

    const resp = await apiPost('/api/eap-alarm/spool', body, { timeout: 60000 });
    const respObj = resp as Record<string, unknown>;
    const respData = (respObj?.data || {}) as Record<string, unknown>;

    // EAP ALARM is always-async (Type B, no sync fallback).
    if (respObj?._status === 202 || respData.async === true || respData.job_id) {
      const jobId = (respData.job_id as string) ?? '';
      const statusUrl =
        (respData.status_url as string | undefined) ??
        `/api/eap-alarm/spool/status?query_id=${encodeURIComponent(respData.query_id as string ?? '')}`;
      const preQueryId = (respData.query_id as string) ?? '';

      jobProgress.active = true;
      jobProgress.jobId = jobId;
      jobProgress.status = 'queued';
      jobProgress.progress = '';
      jobProgress.pct = 0;
      jobProgress.elapsedSeconds = 0;

      const controller = new AbortController();
      _jobAbortController = controller;

      try {
        await pollJobUntilComplete(statusUrl, {
          signal: controller.signal,
          onProgress: (statusResp) => {
            jobProgress.status = statusResp.status;
            jobProgress.progress = (statusResp.progress as string) || '';
            jobProgress.pct = (statusResp.pct as number) || 0;
            jobProgress.elapsedSeconds = (statusResp.elapsed_seconds as number) || 0;
          },
        });
      } finally {
        if (_jobAbortController === controller) _jobAbortController = null;
        jobProgress.active = false;
      }

      // Spool complete — set queryId and load filter options + views
      setQueryId(preQueryId);
      await _loadAfterSpool(preQueryId);
      return;
    }

    // Unexpected sync response
    errorMessage.value = '未預期的查詢回應，請重試';
  } catch (err) {
    const e = err as Record<string, unknown>;
    if (e?.name === 'AbortError') {
      errorMessage.value = '查詢已取消';
    } else if (e?.errorCode === 'JOB_FAILED') {
      errorMessage.value = String(e?.message || '背景查詢失敗');
    } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
      errorMessage.value = '背景查詢超時，請稍後重試';
    } else {
      errorMessage.value = String(e?.message || 'EAP ALARM 查詢失敗');
    }
  } finally {
    queryLoading.value = false;
    jobProgress.active = false;
  }
}

async function _loadAfterSpool(qId: string): Promise<void> {
  // Fetch filter options first, then load views
  const options = await fetchFilterOptions(qId);
  if (options) {
    applyFilterOptions(options);
  }
  const params = buildFineFilterParams();
  await fetchAllViews(qId, params);
}

function handleClear(): void {
  cancelAsyncJob();
  coarseFilter.machines = [];
  errorMessage.value = '';
  queryLoading.value = false;
  queryId.value = '';
  spoolReady.value = false;
  resetFineFilter();
  resetFilterOptions();
  resetViews();
  setDefaultDateRange();
}

async function handleGranularityChange(value: string): Promise<void> {
  trendGranularity.value = value;
  if (!queryId.value) return;
  const params = buildFineFilterParams();
  await fetchTrend(queryId.value, params, value);
}

async function handleDetailPageChange(page: number): Promise<void> {
  if (!queryId.value) return;
  detailPage.value = page;
  const params = buildFineFilterParams();
  await fetchDetail(queryId.value, params, page, detailPerPage.value);
}

async function handleFineFilterChange(): Promise<void> {
  if (!queryId.value) return;
  detailPage.value = 1;
  const params = buildFineFilterParams();
  await fetchAllViews(queryId.value, params);
}

async function handleParetoClick(alarmText: string): Promise<void> {
  if (!queryId.value) return;
  // Add clicked alarm_text to fine filter
  if (!fineFilter.alarm_text.includes(alarmText)) {
    fineFilter.alarm_text = [...fineFilter.alarm_text, alarmText];
  }
}
</script>

<template>
  <div class="theme-eap-alarm">
    <!-- Page-level loading overlay — hide when async job is active (css-contract 4.6) -->
    <LoadingOverlay
      v-if="queryLoading && !jobProgress.active"
      tier="page"
    />

    <!-- Async job progress bar (always-async EAP ALARM) -->
    <AsyncQueryProgress
      :active="jobProgress.active"
      :progress="jobProgress.progress"
      :pct="jobProgress.pct"
      :elapsed-seconds="jobProgress.elapsedSeconds"
      :status="jobProgress.status"
      :can-cancel="true"
      @cancel="cancelAsyncJob"
    />

    <div class="resource-page">
      <div class="header-gradient dashboard">
        <div class="dashboard-inner">
          <h1>EAP ALARM 分析</h1>
        </div>
      </div>

      <div class="dashboard dashboard-inner page-content">
        <!-- Error banner -->
        <ErrorBanner
          v-if="errorMessage || viewError"
          :message="errorMessage || viewError"
        />

        <!-- Coarse filter bar -->
        <FilterBar
          :filters="coarseFilter"
          :resource-options="resourceOptions"
          :loading="{ querying: queryLoading }"
          @submit="handleSubmit"
          @clear="handleClear"
        />

        <!-- Results (only after spool complete and queryId set) -->
        <template v-if="spoolReady && queryId">
          <!-- Fine filter bar -->
          <FineFilterBar
            :fine-filter="fineFilter"
            :filter-options="filterOptions"
            @change="handleFineFilterChange"
          />

          <!-- Summary cards -->
          <SummaryCards
            :summary="summary"
            :loading="viewLoading.summary"
          />

          <!-- Charts row -->
          <div class="charts-row">
            <ParetoChart
              :items="pareto.items"
              :total="pareto.total"
              :loading="viewLoading.pareto"
              @bar-click="handleParetoClick"
            />
            <TrendChart
              :labels="trend.labels"
              :series="trend.series"
              :granularity="trendGranularity"
              :loading="viewLoading.trend"
              @granularity-change="handleGranularityChange"
            />
          </div>

          <!-- Detail table -->
          <DetailTable
            :rows="detail.rows"
            :meta="detail.meta"
            :loading="viewLoading.detail"
            @go-to-page="handleDetailPageChange"
          />

          <!-- Zero-results state after spool returns empty -->
          <EmptyState
            v-if="hasNoResults"
            type="no-results"
            message="目前篩選條件無 ALARM 資料，請調整細部篩選或擴大日期範圍"
          />
        </template>

        <!-- Empty state before first query -->
        <EmptyState
          v-else-if="!queryLoading && !jobProgress.active && !spoolReady"
          type="default"
          message="請選擇查詢條件後按「查詢」以開始分析"
        />
      </div>
    </div>
  </div>
</template>
