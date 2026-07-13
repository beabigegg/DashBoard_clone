<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';

import { apiPost } from '../core/api';
import { pollJobUntilComplete } from '../shared-composables/useAsyncJobPolling';

import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import AsyncQueryProgress from '../shared-ui/components/AsyncQueryProgress.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';

import FilterBar from './FilterBar.vue';
import FineFilterBar from './FineFilterBar.vue';
import TrendChart from './TrendChart.vue';
import RankingBlock from './RankingBlock.vue';
import DetailTable from './DetailTable.vue';

import { useUphPerformanceFilter } from './composables/useUphPerformanceFilter';
import { useUphPerformanceViews } from './composables/useUphPerformanceViews';

// ── Composables ────────────────────────────────────────────────────────────────
const {
  coarseFilter,
  fineFilter,
  rankingTypeFilter,
  filterOptions,
  productFilterOptions,
  productOptionsLoading,
  productOptionsError,
  queryId,
  spoolReady,
  setQueryId,
  resetFineFilter,
  resetFilterOptions,
  resetRankingTypeFilter,
  applyFilterOptions,
  buildFineFilterParams,
  buildCoarseParams,
  setDefaultDateRange,
} = useUphPerformanceFilter();

const {
  loading: viewLoading,
  error: viewError,
  trend,
  trendGroupBy,
  ranking,
  detail,
  detailPage,
  detailPerPage,
  resetAll: resetViews,
  fetchFilterOptions,
  fetchAllViews,
  fetchTrend,
  fetchRanking,
  fetchDetail,
} = useUphPerformanceViews();

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

// state-empty discriminator: spool succeeded, zero rows for this window/
// filter combination — distinct from state-job-failed / state-unavailable
// (interaction-design.md §States, §Consistency Commitments).
const hasNoResults = computed(
  () =>
    spoolReady.value &&
    queryId.value &&
    !viewLoading.detail &&
    detail.meta.total_count === 0,
);

// ── Initial mount ─────────────────────────────────────────────────────────────
onMounted(() => {
  setDefaultDateRange();
});

// ── Fine filter watcher: re-fetch trend + detail on change (ranking has its
//    own independent axis and is never driven by the fine filter bar) ───────
watch(
  () => [
    fineFilter.equipment_id,
    fineFilter.workcenter_name,
    fineFilter.package,
    fineFilter.pj_type,
  ],
  async () => {
    if (!queryId.value) return;
    detailPage.value = 1;
    const params = buildFineFilterParams();
    await Promise.all([
      fetchTrend(queryId.value, params, trendGroupBy.value),
      fetchDetail(queryId.value, params, 1, detailPerPage.value),
    ]);
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
  resetRankingTypeFilter();
  resetViews();

  try {
    const body = buildCoarseParams();

    const resp = await apiPost('/api/uph-performance/spool', body, { timeout: 60000 });
    const respObj = resp as Record<string, unknown>;
    const respData = (respObj?.data || {}) as Record<string, unknown>;

    // UPH-Performance is always-async (Type B, no sync fallback) — a spool
    // hit still comes back through this same POST with async:false.
    if (respData.async === false && respData.query_id) {
      setQueryId(respData.query_id as string);
      await _loadAfterSpool(respData.query_id as string);
      return;
    }

    if (respObj?._status === 202 || respData.async === true || respData.job_id) {
      const jobId = (respData.job_id as string) ?? '';
      const statusUrl =
        (respData.status_url as string | undefined) ??
        `/api/uph-performance/spool/status?query_id=${encodeURIComponent(respData.query_id as string ?? '')}`;
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

    // Unexpected response shape
    errorMessage.value = '未預期的查詢回應，請重試';
  } catch (err) {
    const e = err as Record<string, unknown>;
    if (e?.name === 'AbortError') {
      errorMessage.value = '查詢已取消';
    } else if (e?.errorCode === 'JOB_FAILED') {
      errorMessage.value = String(e?.message || '背景查詢失敗');
    } else if (e?.errorCode === 'JOB_POLL_TIMEOUT') {
      errorMessage.value = '背景查詢超時，請稍後重試';
    } else if (e?.status === 503) {
      errorMessage.value = String(e?.message || '背景查詢服務暫時無法使用，請稍後再試');
    } else {
      errorMessage.value = String(e?.message || 'UPH 表現查詢失敗');
    }
  } finally {
    queryLoading.value = false;
    jobProgress.active = false;
  }
}

async function _loadAfterSpool(qId: string): Promise<void> {
  // Fetch filter options first (feeds both the fine-filter bar and the
  // ranking block's own Type option list), then load trend + detail. Ranking
  // itself stays un-queried (fetchRanking guards on an empty selection).
  const options = await fetchFilterOptions(qId);
  if (options) {
    applyFilterOptions(options);
  }
  const params = buildFineFilterParams();
  await fetchAllViews(qId, params, rankingTypeFilter.value);
}

function handleClear(): void {
  cancelAsyncJob();
  coarseFilter.families = [];
  coarseFilter.workcenter_names = [];
  coarseFilter.packages = [];
  coarseFilter.pj_types = [];
  coarseFilter.equipment_ids = [];
  errorMessage.value = '';
  queryLoading.value = false;
  queryId.value = '';
  spoolReady.value = false;
  resetFineFilter();
  resetFilterOptions();
  resetRankingTypeFilter();
  resetViews();
  setDefaultDateRange();
}

async function handleTrendGroupByChange(value: string): Promise<void> {
  trendGroupBy.value = value;
  if (!queryId.value) return;
  const params = buildFineFilterParams();
  await fetchTrend(queryId.value, params, value);
}

async function handleRankingTypeChange(values: string[]): Promise<void> {
  rankingTypeFilter.value = values;
  if (!queryId.value) return;
  await fetchRanking(queryId.value, values);
}

async function handleDetailPageChange(page: number): Promise<void> {
  if (!queryId.value) return;
  detailPage.value = page;
  const params = buildFineFilterParams();
  await fetchDetail(queryId.value, params, page, detailPerPage.value);
}

async function handleFineFilterChange(): Promise<void> {
  // Watcher above handles the actual re-fetch; this handler exists so
  // FineFilterBar's @change has an explicit target (mirrors eap-alarm).
}
</script>

<template>
  <div class="theme-uph-performance" data-testid="uph-performance-app">
    <!-- Page-level loading overlay — hide when async job is active (css-contract 4.6) -->
    <LoadingOverlay
      v-if="queryLoading && !jobProgress.active"
      tier="page"
      data-testid="loading-state"
    />

    <!-- Async job progress bar (always-async UPH-Performance) -->
    <AsyncQueryProgress
      :active="jobProgress.active"
      :progress="jobProgress.progress"
      :pct="jobProgress.pct"
      :elapsed-seconds="jobProgress.elapsedSeconds"
      :status="jobProgress.status"
      :can-cancel="true"
      @cancel="cancelAsyncJob"
    />

    <div class="dashboard page-content">
      <!-- Error banner (state-unavailable / state-validation-error /
           state-job-failed / state-expired — same visual language, never
           swapped with EmptyState per consistency commitment) -->
      <ErrorBanner
        v-if="errorMessage || viewError"
        :message="errorMessage || viewError"
        data-testid="error-banner"
      />

      <!-- Coarse filter bar -->
      <FilterBar
        :filters="coarseFilter"
        :product-filter-options="productFilterOptions"
        :product-options-loading="productOptionsLoading"
        :product-options-error="productOptionsError"
        :loading="{ querying: queryLoading }"
        @update:filters="(val) => Object.assign(coarseFilter, val)"
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

        <!-- Trend chart -->
        <TrendChart
          :labels="trend.labels"
          :series="trend.series"
          :group-by="trendGroupBy"
          :loading="viewLoading.trend"
          @group-by-change="handleTrendGroupByChange"
        />

        <!-- Equipment ranking (own independent Type filter) -->
        <RankingBlock
          :items="ranking.items"
          :type-options="filterOptions.pj_type_options"
          :selected-types="rankingTypeFilter"
          :loading="viewLoading.ranking"
          @update:selected-types="handleRankingTypeChange"
        />

        <!-- Detail table -->
        <DetailTable
          :rows="detail.rows"
          :meta="detail.meta"
          :loading="viewLoading.detail"
          @go-to-page="handleDetailPageChange"
        />

        <!-- Zero-results state after spool returns empty (state-empty) -->
        <EmptyState
          v-if="hasNoResults"
          type="no-data"
          message="此範圍無 UPH 資料，請放寬日期或調整篩選器"
          data-testid="empty-state"
        />
      </template>

      <!-- state-initial: nothing run yet -->
      <EmptyState
        v-else-if="!queryLoading && !jobProgress.active && !spoolReady"
        type="no-data"
        message="請選擇查詢條件後按「查詢」以開始分析"
        data-testid="empty-state"
      />
    </div>
  </div>
</template>
