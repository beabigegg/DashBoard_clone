<script setup>
import { computed, onMounted, ref } from 'vue';

import DauTrendChart from '../components/DauTrendChart.vue';
import DeptBreakdownTable from '../components/DeptBreakdownTable.vue';
import DurationDistChart from '../components/DurationDistChart.vue';
import HourlyLoginChart from '../components/HourlyLoginChart.vue';
import KpiCard from '../components/KpiCard.vue';
import RecentSessionsTable from '../components/RecentSessionsTable.vue';
import TopUsersTable from '../components/TopUsersTable.vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import LoadingSpinner from '../../shared-ui/components/LoadingSpinner.vue';
import SectionCard from '../../shared-ui/components/SectionCard.vue';
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import TrendChart from '../../admin-shared/components/TrendChart.vue';
import { usePerfHistory, useUsageKpi } from '../../admin-shared/composables/useAdminData';
import { useLastUpdated } from '../../admin-shared/composables/useLastUpdated';

const startDate = ref('');
const endDate = ref('');
const department = ref('');

const usageHook = useUsageKpi(startDate, endDate, department);
const historyHook = usePerfHistory(60, 30);
const { lastUpdatedLabel, markUpdated } = useLastUpdated();

const kpiData = computed(() => usageHook.data.value || null);
const loading = computed(() => usageHook.loading.value);
const error = computed(() => usageHook.error.value);
const onlineTrendData = computed(() => historyHook.data.value || []);

const onlineTrendSeries = [
  { name: '在線人數', key: 'online_count', color: 'var(--color-accent-500)' },
];

function initDates() {
  const now = new Date();
  endDate.value = now.toISOString().slice(0, 10);
  const start = new Date(now);
  start.setDate(start.getDate() - 30);
  startDate.value = start.toISOString().slice(0, 10);
}

function formatSessionDuration(seconds) {
  if (seconds == null || seconds === 0) return '-';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

async function refresh() {
  await Promise.all([usageHook.refresh(), historyHook.refresh()]);
  markUpdated();
}

defineExpose({ refresh });

onMounted(() => {
  initDates();
  void refresh();
});
</script>

<template>
  <div class="usage-tab">
    <div class="admin-tab__last-updated" role="status" aria-live="polite">{{ lastUpdatedLabel }}</div>
    <section class="panel">
      <h2 class="panel-title">用戶 KPI</h2>
      <div class="usage-filter-bar">
        <label>
          起始
          <input type="date" v-model="startDate" />
        </label>
        <label>
          結束
          <input type="date" v-model="endDate" />
        </label>
        <select v-model="department">
          <option value="">全部部門</option>
          <option v-for="item in kpiData?.departments_available || []" :key="item" :value="item">
            {{ item }}
          </option>
        </select>
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :class="{ 'is-loading': loading }"
          :disabled="loading"
          @click="refresh"
        >
          <LoadingSpinner v-if="loading" size="sm" />
          {{ loading ? '查詢中...' : '查詢' }}
        </button>
      </div>
    </section>

    <ErrorBanner :message="error" :dismissible="false" />

    <section v-if="loading && !kpiData" class="panel">
      <BlockLoadingState />
    </section>

    <template v-if="kpiData">
      <SectionCard>
        <template #header><h2 class="panel-title">總覽</h2></template>
        <SummaryCardGroup :columns="4">
          <SummaryCard label="不重複使用者" :value="kpiData.overview?.unique_users" accent="brand" />
          <SummaryCard label="總登入次數" :value="kpiData.overview?.total_sessions" accent="info" />
          <SummaryCard label="平均使用時長" :value="formatSessionDuration(kpiData.overview?.avg_duration_sec)" accent="success" />
          <SummaryCard label="目前在線" :value="kpiData.overview?.active_sessions" accent="warning" />
        </SummaryCardGroup>
      </SectionCard>

      <SectionCard>
        <template #header><h2 class="panel-title">每日活躍使用者（DAU）</h2></template>
        <DauTrendChart :data="kpiData.dau_trend || []" />
      </SectionCard>

      <SectionCard>
        <template #header><h2 class="panel-title">在線人數趨勢（近 60 分鐘）</h2></template>
        <TrendChart
          :snapshots="onlineTrendData"
          :series="onlineTrendSeries"
          title="在線人數"
          yAxisLabel="人"
          height="200px"
        />
      </SectionCard>

      <div class="charts-grid">
        <SectionCard>
          <template #header><h2 class="panel-title">登入時段分佈</h2></template>
          <HourlyLoginChart :data="kpiData.hourly_logins || []" />
        </SectionCard>
        <SectionCard>
          <template #header><h2 class="panel-title">使用時長分佈</h2></template>
          <DurationDistChart :data="kpiData.duration_distribution || []" />
        </SectionCard>
      </div>

      <div class="tables-grid">
        <SectionCard>
          <template #header><h2 class="panel-title">Top 使用者</h2></template>
          <TopUsersTable :users="kpiData.top_users || []" />
        </SectionCard>
        <SectionCard>
          <template #header><h2 class="panel-title">部門統計</h2></template>
          <DeptBreakdownTable :departments="kpiData.dept_breakdown || []" />
        </SectionCard>
      </div>

      <SectionCard>
        <template #header><h2 class="panel-title">近期登入記錄</h2></template>
        <RecentSessionsTable :sessions="kpiData.recent_sessions || []" />
      </SectionCard>
    </template>
  </div>
</template>
