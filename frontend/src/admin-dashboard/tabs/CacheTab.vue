<script setup>
import { computed, onMounted } from 'vue';

import GaugeBar from '../../admin-shared/components/GaugeBar.vue';
import StatCard from '../../admin-shared/components/StatCard.vue';
import TrendChart from '../../admin-shared/components/TrendChart.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import SectionCard from '../../shared-ui/components/SectionCard.vue';
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
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
    <ErrorBanner :message="errorMessage" :dismissible="false" />

    <SectionCard v-if="perfDetail?.redis">
      <template #header><h2 class="panel-title">Redis 快取</h2></template>
      <div class="redis-grid">
        <div class="redis-stats">
          <GaugeBar
            label="記憶體使用"
            :value="redisMemoryRatio"
            :max="1"
            :displayText="redisMemoryLabel"
          />
          <SummaryCardGroup :columns="2">
            <SummaryCard label="已使用" :value="perfDetail.redis.used_memory_human" accent="info" />
            <SummaryCard label="峰值" :value="perfDetail.redis.peak_memory_human" accent="warning" />
            <SummaryCard label="連線數" :value="perfDetail.redis.connected_clients" accent="brand" />
            <SummaryCard label="命中率" :value="hitRateDisplay" accent="success" />
          </SummaryCardGroup>
        </div>
        <div class="redis-namespaces">
          <DataTable :data="perfDetail.redis.namespaces || []">
            <DataTableColumn columnKey="name" label="Namespace" />
            <DataTableColumn columnKey="key_count" label="Key 數量" align="right" />
          </DataTable>
        </div>
      </div>
    </SectionCard>
    <SectionCard v-else-if="perfDetail && !perfDetail.redis">
      <template #header><h2 class="panel-title">Redis 快取</h2></template>
      <p class="muted">Redis 未啟用</p>
    </SectionCard>

    <TrendChart
      v-if="historyData.length > 1"
      title="Redis 記憶體趨勢"
      :snapshots="historyData"
      :series="redisTrendSeries"
    />

    <SectionCard v-if="perfDetail">
      <template #header><h2 class="panel-title">記憶體快取</h2></template>
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
        <SummaryCardGroup :columns="6">
          <SummaryCard label="模式" :value="perfDetail.route_cache.mode" accent="neutral" />
          <SummaryCard label="L1 大小" :value="perfDetail.route_cache.l1_size" accent="info" />
          <SummaryCard label="L1 命中率" :value="routeCacheL1HitRate" accent="success" />
          <SummaryCard label="L2 命中率" :value="routeCacheL2HitRate" accent="brand" />
          <SummaryCard label="未命中率" :value="routeCacheMissRate" accent="warning" />
          <SummaryCard label="總讀取" :value="perfDetail.route_cache.reads_total" accent="info" />
        </SummaryCardGroup>
      </div>
    </SectionCard>

    <SectionCard
      v-if="perfDetail?.pareto_materialization && !perfDetail.pareto_materialization.error"
    >
      <template #header><h2 class="panel-title">Pareto 物化層</h2></template>
      <SummaryCardGroup :columns="5">
        <SummaryCard label="命中率" :value="paretoHitRateDisplay" accent="success" />
        <SummaryCard label="命中次數" :value="perfDetail.pareto_materialization.hit" accent="success" />
        <SummaryCard label="未命中次數" :value="perfDetail.pareto_materialization.miss" accent="warning" />
        <SummaryCard label="建構次數" :value="perfDetail.pareto_materialization.build" accent="info" />
        <SummaryCard label="建構成功" :value="perfDetail.pareto_materialization.build_ok" accent="success" />
        <SummaryCard label="建構失敗" :value="perfDetail.pareto_materialization.build_fail" accent="danger" />
        <SummaryCard label="Fallback 次數" :value="perfDetail.pareto_materialization.fallback" accent="warning" />
        <SummaryCard label="超大拒絕" :value="perfDetail.pareto_materialization.rejected_oversize" accent="danger" />
        <SummaryCard label="最近建構耗時" :value="paretoBuildLatencyDisplay" accent="neutral" />
        <SummaryCard label="Snapshot 大小" :value="paretoPayloadDisplay" accent="neutral" />
      </SummaryCardGroup>
      <div class="pareto-fallback-reasons" v-if="paretoFallbackReasons.length">
        <h3 class="sub-title">Fallback 原因分布</h3>
        <DataTable :data="paretoFallbackReasons">
          <DataTableColumn columnKey="reason" label="原因" />
          <DataTableColumn columnKey="count" label="次數" align="right" />
        </DataTable>
      </div>
    </SectionCard>

    <TrendChart
      v-if="historyData.length > 1"
      title="快取命中率趨勢"
      :snapshots="historyData"
      :series="hitRateTrendSeries"
      :yMax="1"
    />
  </div>
</template>
