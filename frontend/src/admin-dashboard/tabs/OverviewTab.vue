<script setup>
import { computed, onMounted } from 'vue';

import StatusDot from '../../admin-shared/components/StatusDot.vue';
import TrendChart from '../../admin-shared/components/TrendChart.vue';
import { useHealthSummary, usePerfHistory } from '../../admin-shared/composables/useAdminData.js';

const healthHook = useHealthSummary();
const historyHook = usePerfHistory(30, 30);

const healthData = computed(() => healthHook.data.value || {});
const historyData = computed(() => historyHook.data.value || []);
const services = computed(() => healthData.value?.services || {});
const warnings = computed(() => {
  if (!Array.isArray(healthData.value?.warnings)) return [];
  return healthData.value.warnings;
});

const asyncWorkers = computed(() => healthData.value?.async_workers || {});
const workerSummary = computed(() => asyncWorkers.value?.workers?.summary || {});
const queueSummary = computed(() => asyncWorkers.value?.queues || {});

const queueDepth = computed(
  () => queueSummary.value?.total_queued ?? queueSummary.value?.total_depth ?? 0,
);
const workersTotal = computed(() => workerSummary.value?.total ?? 0);

function mapServiceStatus(rawStatus) {
  if (rawStatus === 'healthy' || rawStatus === 'ok') return 'healthy';
  if (rawStatus === 'error') return 'error';
  if (rawStatus === 'disabled') return 'disabled';
  return 'degraded';
}

const dbStatus = computed(() => mapServiceStatus(services.value?.database));
const redisStatus = computed(() => mapServiceStatus(services.value?.redis));

const circuitState = computed(() => healthData.value?.circuit_breaker?.state || '-');
const circuitStatus = computed(() => {
  if (circuitState.value === 'CLOSED') return 'healthy';
  if (circuitState.value === 'OPEN') return 'error';
  if (circuitState.value === 'HALF_OPEN') return 'degraded';
  return 'disabled';
});

const memoryInfo = computed(() => healthData.value?.system_memory || {});
const memoryStatus = computed(() => {
  const pressure = memoryInfo.value?.pressure;
  if (pressure === 'high') return 'error';
  if (pressure === 'medium') return 'degraded';
  if (typeof memoryInfo.value?.used_pct === 'number') return 'healthy';
  return 'disabled';
});

const memoryLabel = computed(() => {
  const usedPct = memoryInfo.value?.used_pct;
  const total = memoryInfo.value?.total_mb;
  const available = memoryInfo.value?.available_mb;
  if (
    typeof usedPct === 'number'
    && typeof total === 'number'
    && typeof available === 'number'
  ) {
    const used = Math.max(0, total - available);
    return `${usedPct.toFixed(1)}% (${used.toFixed(0)}MB / ${total.toFixed(0)}MB)`;
  }
  return '資料不足';
});

const dbMetric = computed(() => {
  const saturation = healthData.value?.database_pool?.state?.saturation;
  if (typeof saturation === 'number') {
    return `Pool ${(saturation * 100).toFixed(1)}%`;
  }
  return `狀態 ${services.value?.database || '-'}`;
});

const redisMetric = computed(() => {
  const serviceStatus = services.value?.redis || '-';
  const redisHitRate =
    historyData.value?.[historyData.value.length - 1]?.redis_hit_rate;
  if (typeof redisHitRate === 'number') {
    return `Hit ${(redisHitRate * 100).toFixed(1)}%`;
  }
  return `狀態 ${serviceStatus}`;
});

const deadWorkerAlert = computed(() => {
  if (asyncWorkers.value?.rq_available === false) return true;
  if (queueDepth.value > 0 && workersTotal.value === 0) return true;
  return warnings.value.some((entry) => String(entry || '').includes('RQ Worker 離線'));
});

const latencyMiniSeries = [
  { name: 'P95', key: 'latency_p95_ms', color: '#f59e0b' },
];

const poolMiniSeries = [
  { name: '飽和度', key: 'pool_saturation', color: '#2563eb' },
];

const workerMiniSeries = [
  { name: 'RSS', key: 'worker_rss_mb', color: '#8b5cf6' },
];

const cacheMiniSeries = [
  { name: 'Hit Rate', key: 'redis_hit_rate', color: '#10b981' },
];

const isInitialLoading = computed(
  () => healthHook.loading.value && !healthHook.data.value && !healthHook.error.value,
);

const errorMessage = computed(() => healthHook.error.value || historyHook.error.value || '');

async function refresh() {
  await Promise.all([healthHook.refresh(), historyHook.refresh()]);
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="overview-tab">
    <section v-if="isInitialLoading" class="panel">
      <div class="loading-text">載入總覽資料中...</div>
    </section>

    <section v-if="errorMessage" class="panel panel-disabled">
      <div class="muted">{{ errorMessage }}</div>
    </section>

    <section class="panel">
      <h2 class="panel-title">系統健康總覽</h2>
      <div class="status-cards-grid">
        <div class="status-card">
          <div class="status-card-title">Database</div>
          <StatusDot :status="dbStatus" :label="services?.database || '-'" />
          <div class="status-card-meta">{{ dbMetric }}</div>
        </div>
        <div class="status-card">
          <div class="status-card-title">Redis</div>
          <StatusDot :status="redisStatus" :label="services?.redis || '-'" />
          <div class="status-card-meta">{{ redisMetric }}</div>
        </div>
        <div class="status-card">
          <div class="status-card-title">Circuit Breaker</div>
          <StatusDot :status="circuitStatus" :label="circuitState" />
          <div class="status-card-meta">狀態監控</div>
        </div>
        <div class="status-card">
          <div class="status-card-title">System Memory</div>
          <StatusDot :status="memoryStatus" :label="memoryLabel" />
          <div class="status-card-meta">{{ memoryInfo?.pressure || 'normal' }}</div>
        </div>
      </div>
    </section>

    <section v-if="deadWorkerAlert" class="overview-warning-banner">
      ⚠️ 偵測到 RQ worker 可能離線（queue_depth={{ queueDepth }} / workers={{ workersTotal }}）
    </section>

    <section class="panel">
      <h2 class="panel-title">30 分鐘趨勢</h2>
      <div class="overview-mini-grid">
        <TrendChart
          :snapshots="historyData"
          :series="latencyMiniSeries"
          title="查詢延遲 P95"
          yAxisLabel="ms"
          height="180px"
        />
        <TrendChart
          :snapshots="historyData"
          :series="poolMiniSeries"
          title="連線池飽和度"
          yAxisLabel="%"
          :yMax="1"
          height="180px"
        />
        <TrendChart
          :snapshots="historyData"
          :series="workerMiniSeries"
          title="Worker 記憶體"
          yAxisLabel="MB"
          height="180px"
        />
        <TrendChart
          :snapshots="historyData"
          :series="cacheMiniSeries"
          title="Cache 命中率"
          yAxisLabel="%"
          :yMax="1"
          height="180px"
        />
      </div>
    </section>

    <section class="panel">
      <h2 class="panel-title">Active Alerts</h2>
      <ul v-if="warnings.length" class="overview-alert-list">
        <li v-for="(entry, index) in warnings" :key="`${entry}-${index}`">
          {{ entry }}
        </li>
      </ul>
      <p v-else class="muted">目前無警示訊息</p>
    </section>
  </div>
</template>
