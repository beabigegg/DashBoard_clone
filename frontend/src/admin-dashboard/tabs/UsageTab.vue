<script setup>
import { computed, onMounted, ref } from 'vue';

import DauTrendChart from '../../admin-user-usage-kpi/components/DauTrendChart.vue';
import DeptBreakdownTable from '../../admin-user-usage-kpi/components/DeptBreakdownTable.vue';
import DurationDistChart from '../../admin-user-usage-kpi/components/DurationDistChart.vue';
import HourlyLoginChart from '../../admin-user-usage-kpi/components/HourlyLoginChart.vue';
import KpiCard from '../../admin-user-usage-kpi/components/KpiCard.vue';
import RecentSessionsTable from '../../admin-user-usage-kpi/components/RecentSessionsTable.vue';
import TopUsersTable from '../../admin-user-usage-kpi/components/TopUsersTable.vue';
import { useUsageKpi } from '../../admin-shared/composables/useAdminData.js';

const startDate = ref('');
const endDate = ref('');
const department = ref('');

const usageHook = useUsageKpi(startDate, endDate, department);

const kpiData = computed(() => usageHook.data.value || null);
const loading = computed(() => usageHook.loading.value);
const error = computed(() => usageHook.error.value);

function initDates() {
  const now = new Date();
  endDate.value = now.toISOString().slice(0, 10);
  const start = new Date(now);
  start.setDate(start.getDate() - 30);
  startDate.value = start.toISOString().slice(0, 10);
}

function formatDuration(seconds) {
  if (seconds == null || seconds === 0) return '-';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

async function refresh() {
  await usageHook.refresh();
}

defineExpose({ refresh });

onMounted(() => {
  initDates();
  void refresh();
});
</script>

<template>
  <div class="usage-tab">
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
        <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="refresh" :disabled="loading">
          {{ loading ? '載入中...' : '查詢' }}
        </button>
      </div>
    </section>

    <section v-if="error" class="panel panel-disabled">
      <p class="muted">{{ error }}</p>
    </section>

    <section v-if="loading && !kpiData" class="panel">
      <div class="loading-text">載入中...</div>
    </section>

    <template v-if="kpiData">
      <section class="panel">
        <h2 class="panel-title">總覽</h2>
        <div class="kpi-cards-grid">
          <KpiCard :value="kpiData.overview?.unique_users" label="不重複使用者" />
          <KpiCard :value="kpiData.overview?.total_sessions" label="總登入次數" />
          <KpiCard :value="formatDuration(kpiData.overview?.avg_duration_sec)" label="平均使用時長" />
          <KpiCard :value="kpiData.overview?.active_sessions" label="目前在線" />
        </div>
      </section>

      <section class="panel">
        <h2 class="panel-title">每日活躍使用者（DAU）</h2>
        <DauTrendChart :data="kpiData.dau_trend || []" />
      </section>

      <div class="charts-grid">
        <section class="panel">
          <h2 class="panel-title">登入時段分佈</h2>
          <HourlyLoginChart :data="kpiData.hourly_logins || []" />
        </section>
        <section class="panel">
          <h2 class="panel-title">使用時長分佈</h2>
          <DurationDistChart :data="kpiData.duration_distribution || []" />
        </section>
      </div>

      <div class="tables-grid">
        <section class="panel">
          <h2 class="panel-title">Top 使用者</h2>
          <TopUsersTable :users="kpiData.top_users || []" />
        </section>
        <section class="panel">
          <h2 class="panel-title">部門統計</h2>
          <DeptBreakdownTable :departments="kpiData.dept_breakdown || []" />
        </section>
      </div>

      <section class="panel">
        <h2 class="panel-title">近期登入記錄</h2>
        <RecentSessionsTable :sessions="kpiData.recent_sessions || []" />
      </section>
    </template>
  </div>
</template>
