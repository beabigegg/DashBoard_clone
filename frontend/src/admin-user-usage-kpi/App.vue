<script setup>
import { onMounted, ref } from 'vue';

import { apiGet } from '../core/api.js';
import BlockLoadingState from '../shared-ui/components/BlockLoadingState.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import DauTrendChart from './components/DauTrendChart.vue';
import DeptBreakdownTable from './components/DeptBreakdownTable.vue';
import DurationDistChart from './components/DurationDistChart.vue';
import HourlyLoginChart from './components/HourlyLoginChart.vue';
import KpiCard from './components/KpiCard.vue';
import RecentSessionsTable from './components/RecentSessionsTable.vue';
import TopUsersTable from './components/TopUsersTable.vue';

const loading = ref(false);
const error = ref('');
const kpiData = ref(null);

// Filter state
const startDate = ref('');
const endDate = ref('');
const department = ref('');

function initDates() {
  const now = new Date();
  endDate.value = now.toISOString().slice(0, 10);
  const start = new Date(now);
  start.setDate(start.getDate() - 30);
  startDate.value = start.toISOString().slice(0, 10);
}

async function fetchData() {
  loading.value = true;
  error.value = '';
  try {
    const data = await apiGet('/admin/api/user-usage-kpi', {
      start_date: startDate.value,
      end_date: endDate.value,
      department: department.value || undefined,
    });
    kpiData.value = data?.data ?? data;
  } catch (e) {
    error.value = e.message || '載入失敗';
    kpiData.value = null;
  } finally {
    loading.value = false;
  }
}

function formatDuration(sec) {
  if (sec == null || sec === 0) return '-';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}

onMounted(() => {
  initDates();
  fetchData();
});
</script>

<template>
  <div class="theme-admin-user-usage-kpi">
    <!-- Header -->
    <header class="kpi-header">
      <div class="kpi-header-inner">
        <h1 class="kpi-title">
          使用者 KPI 儀表板
          <span v-if="kpiData?.source" class="source-badge">{{ kpiData.source }}</span>
        </h1>

        <div class="kpi-filters">
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
            <option v-for="d in kpiData?.departments_available || []" :key="d" :value="d">{{ d }}</option>
          </select>
          <button
            class="ui-btn ui-btn--ghost"
            :class="{ 'is-loading': loading }"
            :disabled="loading"
            @click="fetchData"
          >
            <LoadingSpinner v-if="loading" size="sm" />
            {{ loading ? '查詢中...' : '查詢' }}
          </button>
        </div>
      </div>
    </header>

    <!-- Loading / Error -->
    <BlockLoadingState v-if="loading && !kpiData" />
    <div v-else-if="error" class="panel kpi-error">{{ error }}</div>

    <template v-if="kpiData">
      <!-- Overview Cards -->
      <section class="panel">
        <h2 class="panel-title">總覽</h2>
        <div class="kpi-cards-grid">
          <KpiCard :value="kpiData.overview?.unique_users" label="不重複使用者" />
          <KpiCard :value="kpiData.overview?.total_sessions" label="總登入次數" />
          <KpiCard :value="formatDuration(kpiData.overview?.avg_duration_sec)" label="平均使用時長" />
          <KpiCard :value="kpiData.overview?.active_sessions" label="目前在線" />
        </div>
      </section>

      <!-- Charts -->
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

      <!-- Tables -->
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
