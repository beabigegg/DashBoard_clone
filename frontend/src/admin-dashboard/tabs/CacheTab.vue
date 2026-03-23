<script setup>
import { computed, onMounted } from 'vue';

import GaugeBar from '../../admin-shared/components/GaugeBar.vue';
import StatCard from '../../admin-shared/components/StatCard.vue';
import TrendChart from '../../admin-shared/components/TrendChart.vue';
import {
  usePerfDetail,
  usePerfHistory,
} from '../../admin-shared/composables/useAdminData.js';

const perfDetailHook = usePerfDetail();
const historyHook = usePerfHistory(30, 30);

const perfDetail = computed(() => perfDetailHook.data.value || null);
const historyData = computed(() => historyHook.data.value || []);
const errorMessage = computed(() => perfDetailHook.error.value || historyHook.error.value || '');

const redisMemoryRatio = computed(() => {
  const redis = perfDetail.value?.redis;
  if (!redis) return 0;
  const used = redis.used_memory || 0;
  const max = redis.maxmemory || 0;
  if (max > 0) return used / max;
  const peak = redis.peak_memory || used;
  return peak > 0 ? used / peak : 0;
});

const redisMemoryLabel = computed(() => {
  const redis = perfDetail.value?.redis;
  if (!redis) return '';
  const used = redis.used_memory_human || 'N/A';
  const max = redis.maxmemory && redis.maxmemory > 0
    ? redis.maxmemory_human
    : redis.peak_memory_human;
  return `${used} / ${max || 'N/A'}`;
});

const hitRateDisplay = computed(() => {
  const value = perfDetail.value?.redis?.hit_rate;
  return value != null ? `${(value * 100).toFixed(1)}%` : '-';
});

const routeCacheL1HitRate = computed(() => {
  const value = perfDetail.value?.route_cache?.l1_hit_rate;
  return value != null ? `${(value * 100).toFixed(1)}%` : '-';
});

const routeCacheL2HitRate = computed(() => {
  const value = perfDetail.value?.route_cache?.l2_hit_rate;
  return value != null ? `${(value * 100).toFixed(1)}%` : '-';
});

const routeCacheMissRate = computed(() => {
  const value = perfDetail.value?.route_cache?.miss_rate;
  return value != null ? `${(value * 100).toFixed(1)}%` : '-';
});

const paretoHitRateDisplay = computed(() => {
  const value = perfDetail.value?.pareto_materialization?.hit_rate;
  return value != null ? `${(value * 100).toFixed(1)}%` : '-';
});

const paretoBuildLatencyDisplay = computed(() => {
  const seconds = perfDetail.value?.pareto_materialization?.last_build_latency_s;
  return seconds != null ? `${seconds.toFixed(2)}s` : '-';
});

const paretoPayloadDisplay = computed(() => {
  const bytes = perfDetail.value?.pareto_materialization?.last_snapshot_payload_bytes;
  if (bytes == null) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
});

const paretoFallbackReasons = computed(() => {
  const reasons = perfDetail.value?.pareto_materialization?.fallback_reasons;
  if (!reasons || typeof reasons !== 'object') return [];
  return Object.entries(reasons)
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => ({ reason, count }));
});

const redisTrendSeries = [
  { name: '記憶體 (MB)', key: 'redis_used_memory_mb', color: 'rgb(6, 182, 212)' },
];

const hitRateTrendSeries = [
  { name: 'Redis 命中率', key: 'redis_hit_rate', color: 'rgb(34, 197, 94)' },
  { name: 'L1 命中率', key: 'rc_l1_hit_rate', color: 'rgb(37, 99, 235)' },
  { name: 'L2 命中率', key: 'rc_l2_hit_rate', color: 'rgb(245, 158, 11)' },
];

async function refresh() {
  await Promise.all([
    perfDetailHook.refresh(),
    historyHook.refresh(),
  ]);
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="cache-tab">
    <section v-if="errorMessage" class="panel panel-disabled">
      <div class="muted">{{ errorMessage }}</div>
    </section>

    <section class="panel" v-if="perfDetail?.redis">
      <h2 class="panel-title">Redis 快取</h2>
      <div class="redis-grid">
        <div class="redis-stats">
          <GaugeBar
            label="記憶體使用"
            :value="redisMemoryRatio"
            :max="1"
            :displayText="redisMemoryLabel"
          />
          <div class="redis-mini-stats">
            <StatCard :value="perfDetail.redis.used_memory_human" label="已使用" />
            <StatCard :value="perfDetail.redis.peak_memory_human" label="峰值" />
            <StatCard :value="perfDetail.redis.connected_clients" label="連線數" />
            <StatCard :value="hitRateDisplay" label="命中率" />
          </div>
        </div>
        <div class="redis-namespaces">
          <table class="mini-table">
            <thead><tr><th>Namespace</th><th>Key 數量</th></tr></thead>
            <tbody>
              <tr v-for="namespace in perfDetail.redis.namespaces" :key="namespace.name">
                <td>{{ namespace.name }}</td>
                <td>{{ namespace.key_count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
    <section class="panel panel-disabled" v-else-if="perfDetail && !perfDetail.redis">
      <h2 class="panel-title">Redis 快取</h2>
      <p class="muted">Redis 未啟用</p>
    </section>

    <TrendChart
      v-if="historyData.length > 1"
      title="Redis 記憶體趨勢"
      :snapshots="historyData"
      :series="redisTrendSeries"
    />

    <section class="panel" v-if="perfDetail">
      <h2 class="panel-title">記憶體快取</h2>
      <div class="cache-cards-grid">
        <div class="cache-card" v-for="(info, name) in perfDetail.process_caches" :key="name">
          <div class="cache-card-name">{{ name }}</div>
          <div class="cache-card-desc">{{ info.description }}</div>
          <GaugeBar
            label="使用率"
            :value="info.entries"
            :max="info.max_size"
          />
          <div class="cache-card-ttl">TTL: {{ info.ttl_seconds }}s</div>
        </div>
      </div>
      <div class="route-cache-section" v-if="perfDetail.route_cache">
        <h3 class="sub-title">Route Cache</h3>
        <div class="route-cache-stats">
          <StatCard :value="perfDetail.route_cache.mode" label="模式" />
          <StatCard :value="perfDetail.route_cache.l1_size" label="L1 大小" />
          <StatCard :value="routeCacheL1HitRate" label="L1 命中率" />
          <StatCard :value="routeCacheL2HitRate" label="L2 命中率" />
          <StatCard :value="routeCacheMissRate" label="未命中率" />
          <StatCard :value="perfDetail.route_cache.reads_total" label="總讀取" />
        </div>
      </div>
    </section>

    <section
      class="panel"
      v-if="perfDetail?.pareto_materialization && !perfDetail.pareto_materialization.error"
    >
      <h2 class="panel-title">Pareto 物化層</h2>
      <div class="pareto-stats-grid">
        <StatCard :value="paretoHitRateDisplay" label="命中率" />
        <StatCard :value="perfDetail.pareto_materialization.hit" label="命中次數" />
        <StatCard :value="perfDetail.pareto_materialization.miss" label="未命中次數" />
        <StatCard :value="perfDetail.pareto_materialization.build" label="建構次數" />
        <StatCard :value="perfDetail.pareto_materialization.build_ok" label="建構成功" />
        <StatCard :value="perfDetail.pareto_materialization.build_fail" label="建構失敗" />
        <StatCard :value="perfDetail.pareto_materialization.fallback" label="Fallback 次數" />
        <StatCard :value="perfDetail.pareto_materialization.rejected_oversize" label="超大拒絕" />
        <StatCard :value="paretoBuildLatencyDisplay" label="最近建構耗時" />
        <StatCard :value="paretoPayloadDisplay" label="Snapshot 大小" />
      </div>
      <div class="pareto-fallback-reasons" v-if="paretoFallbackReasons.length">
        <h3 class="sub-title">Fallback 原因分布</h3>
        <table class="mini-table">
          <thead><tr><th>原因</th><th>次數</th></tr></thead>
          <tbody>
            <tr v-for="reason in paretoFallbackReasons" :key="reason.reason">
              <td>{{ reason.reason }}</td>
              <td>{{ reason.count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <TrendChart
      v-if="historyData.length > 1"
      title="快取命中率趨勢"
      :snapshots="historyData"
      :series="hitRateTrendSeries"
      :yMax="1"
    />
  </div>
</template>
