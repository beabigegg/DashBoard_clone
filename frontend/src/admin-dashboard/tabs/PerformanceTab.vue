<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import GaugeBar from '../../admin-shared/components/GaugeBar.vue';
import StatCard from '../../admin-shared/components/StatCard.vue';
import TrendChart from '../../admin-shared/components/TrendChart.vue';
import {
  useMetrics,
  usePerfDetail,
  usePerfHistory,
} from '../../admin-shared/composables/useAdminData.js';

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const metricsHook = useMetrics();
const perfDetailHook = usePerfDetail();
const historyHook = usePerfHistory(30, 30);

const latencyChartRef = ref(null);
let chartInstance = null;

const metricsData = computed(() => metricsHook.data.value || null);
const perfDetail = computed(() => perfDetailHook.data.value || null);
const historyData = computed(() => historyHook.data.value || []);

const errorMessage = computed(
  () => metricsHook.error.value || perfDetailHook.error.value || historyHook.error.value || '',
);

const slowRateDisplay = computed(() => {
  const slowRate = metricsData.value?.slow_rate;
  return slowRate != null ? `${(slowRate * 100).toFixed(1)}%` : '-';
});

const poolOverflowDisplay = computed(() => {
  const overflow = perfDetail.value?.db_pool?.status?.overflow;
  if (overflow == null) return '-';
  return Math.max(0, overflow);
});

const poolTotalConnections = computed(() => {
  const status = perfDetail.value?.db_pool?.status;
  if (!status) return '-';
  return (status.checked_out || 0) + (status.checked_in || 0);
});

const latencyTrendSeries = [
  { name: 'P50', key: 'latency_p50_ms', color: 'rgb(34, 197, 94)' },
  { name: 'P95', key: 'latency_p95_ms', color: 'rgb(245, 158, 11)' },
  { name: 'P99', key: 'latency_p99_ms', color: 'rgb(239, 68, 68)' },
];

const poolTrendSeries = [
  { name: '飽和度', key: 'pool_saturation', color: 'rgb(99, 102, 241)' },
  { name: '使用中', key: 'pool_checked_out', color: 'rgb(245, 158, 11)' },
  { name: '慢查詢執行中', key: 'slow_query_active', color: 'rgb(239, 68, 68)' },
];

function updateLatencyChart() {
  if (!latencyChartRef.value) return;

  if (!chartInstance) {
    chartInstance = echarts.init(latencyChartRef.value);
  }

  const latencies = metricsData.value?.latencies || [];
  if (!latencies.length) {
    chartInstance.clear();
    return;
  }

  const buckets = [
    { label: '<100ms', max: 100 },
    { label: '100-500ms', max: 500 },
    { label: '500ms-1s', max: 1000 },
    { label: '1-5s', max: 5000 },
    { label: '>5s', max: Infinity },
  ];
  const counts = buckets.map(() => 0);
  for (const latencyMs of latencies.map((value) => value * 1000)) {
    for (let index = 0; index < buckets.length; index += 1) {
      if (latencyMs < buckets[index].max || index === buckets.length - 1) {
        counts[index] += 1;
        break;
      }
    }
  }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: buckets.map((bucket) => bucket.label) },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar',
        data: counts,
        itemStyle: { color: 'rgb(99, 102, 241)' },
        barMaxWidth: 40,
      },
    ],
  });
}

async function refresh() {
  await Promise.all([
    metricsHook.refresh(),
    perfDetailHook.refresh(),
    historyHook.refresh(),
  ]);
  updateLatencyChart();
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
});
</script>

<template>
  <div class="performance-tab">
    <section v-if="errorMessage" class="panel panel-disabled">
      <div class="muted">{{ errorMessage }}</div>
    </section>

    <section class="panel">
      <h2 class="panel-title">查詢效能</h2>
      <div class="query-perf-grid">
        <div class="query-perf-stats">
          <StatCard :value="metricsData?.p50_ms" label="P50 (ms)" />
          <StatCard :value="metricsData?.p95_ms" label="P95 (ms)" />
          <StatCard :value="metricsData?.p99_ms" label="P99 (ms)" />
          <StatCard :value="metricsData?.count" label="查詢數" />
          <StatCard :value="metricsData?.slow_count" label="慢查詢" />
          <StatCard :value="slowRateDisplay" label="慢查詢率" />
        </div>
        <div ref="latencyChartRef" class="query-perf-chart"></div>
      </div>
    </section>

    <TrendChart
      v-if="historyData.length > 1"
      title="查詢延遲趨勢"
      :snapshots="historyData"
      :series="latencyTrendSeries"
      yAxisLabel="ms"
    />

    <section v-if="perfDetail?.db_pool?.status" class="panel">
      <h2 class="panel-title">連線池</h2>
      <GaugeBar
        label="飽和度"
        :value="perfDetail.db_pool.status.saturation"
        :max="1"
      />
      <div class="pool-stats-grid">
        <StatCard :value="perfDetail.db_pool.status.checked_out" label="使用中" />
        <StatCard :value="perfDetail.db_pool.status.checked_in" label="閒置" />
        <StatCard :value="poolTotalConnections" label="總連線數" />
        <StatCard :value="perfDetail.db_pool.status.max_capacity" label="最大容量" />
        <StatCard :value="poolOverflowDisplay" label="溢出連線" />
        <StatCard :value="perfDetail.db_pool.status.slow_query_active" label="慢查詢執行中" />
        <StatCard :value="perfDetail.db_pool.status.slow_query_waiting" label="慢查詢排隊中" />
        <StatCard :value="perfDetail.db_pool.config?.pool_size" label="池大小" />
        <StatCard :value="perfDetail.db_pool.config?.pool_recycle" label="回收週期 (s)" />
        <StatCard :value="perfDetail.db_pool.config?.pool_timeout" label="逾時 (s)" />
        <StatCard :value="perfDetail.direct_connections?.total_since_start" label="直連次數" />
      </div>
    </section>

    <TrendChart
      v-if="historyData.length > 1"
      title="連線池趨勢"
      :snapshots="historyData"
      :series="poolTrendSeries"
    />
  </div>
</template>
