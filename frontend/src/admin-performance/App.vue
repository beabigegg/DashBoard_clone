<template>
  <div class="perf-dashboard">
    <!-- Header -->
    <header class="perf-header">
      <div class="perf-header-inner">
        <h1 class="perf-title">效能監控儀表板</h1>
        <div class="perf-header-actions">
          <label class="auto-refresh-toggle">
            <input type="checkbox" v-model="autoRefreshEnabled" @change="toggleAutoRefresh" />
            自動更新 (30s)
          </label>
          <button class="btn btn-sm" @click="refreshAll" :disabled="loading">
            <template v-if="loading">更新中...</template>
            <template v-else>重新整理</template>
          </button>
        </div>
      </div>
    </header>

    <!-- Status Cards -->
    <section class="panel">
      <div class="status-cards-grid">
        <div class="status-card">
          <div class="status-card-title">Database</div>
          <StatusDot :status="dbStatus" :label="dbStatusLabel" />
        </div>
        <div class="status-card">
          <div class="status-card-title">Redis</div>
          <StatusDot :status="redisStatus" :label="redisStatusLabel" />
        </div>
        <div class="status-card">
          <div class="status-card-title">Circuit Breaker</div>
          <StatusDot :status="cbStatus" :label="cbStatusLabel" />
        </div>
        <div class="status-card">
          <div class="status-card-title">Worker PID</div>
          <StatusDot status="healthy" :label="String(systemData?.worker_pid || '-')" />
        </div>
      </div>
    </section>

    <!-- Query Performance -->
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
        <div class="query-perf-chart" ref="latencyChartRef"></div>
      </div>
    </section>

    <!-- Query Latency Trend -->
    <TrendChart
      v-if="historyData.length > 1"
      title="查詢延遲趨勢"
      :snapshots="historyData"
      :series="latencyTrendSeries"
      yAxisLabel="ms"
    />

    <!-- Redis Cache Detail -->
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
              <tr v-for="ns in perfDetail.redis.namespaces" :key="ns.name">
                <td>{{ ns.name }}</td>
                <td>{{ ns.key_count }}</td>
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

    <!-- Redis Memory Trend -->
    <TrendChart
      v-if="historyData.length > 1"
      title="Redis 記憶體趨勢"
      :snapshots="historyData"
      :series="redisTrendSeries"
    />

    <!-- Memory Caches -->
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

    <!-- Pareto Materialization -->
    <section class="panel" v-if="perfDetail?.pareto_materialization && !perfDetail.pareto_materialization.error">
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
            <tr v-for="r in paretoFallbackReasons" :key="r.reason">
              <td>{{ r.reason }}</td>
              <td>{{ r.count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Cache Hit Rate Trend -->
    <TrendChart
      v-if="historyData.length > 1"
      title="快取命中率趨勢"
      :snapshots="historyData"
      :series="hitRateTrendSeries"
      yAxisLabel=""
      :yMax="1"
    />

    <!-- Connection Pool -->
    <section class="panel" v-if="perfDetail?.db_pool?.status">
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

    <!-- Connection Pool Trend -->
    <TrendChart
      v-if="historyData.length > 1"
      title="連線池趨勢"
      :snapshots="historyData"
      :series="poolTrendSeries"
    />

    <!-- Worker Memory Trend -->
    <TrendChart
      v-if="historyData.length > 1"
      title="Worker 記憶體趨勢"
      :snapshots="historyData"
      :series="memoryTrendSeries"
      yAxisLabel="MB"
    />

    <!-- Worker Memory Guard -->
    <section class="panel" v-if="perfDetail?.worker_memory_guard?.enabled">
      <h2 class="panel-title">Worker 記憶體守衛</h2>
      <GaugeBar
        label="RSS 使用率"
        :value="perfDetail.worker_memory_guard.rss_pct"
        :max="100"
        unit="%"
        :displayText="memoryGuardRssDisplay"
        :warningThreshold="0.70"
        :dangerThreshold="0.85"
      />
      <div class="memory-guard-stats">
        <StatCard :value="perfDetail.worker_memory_guard.last_rss_mb?.toFixed(1)" label="當前 RSS (MB)" />
        <StatCard :value="perfDetail.worker_memory_guard.limit_mb" label="上限 (MB)" />
        <StatCard :value="memoryGuardLevelDisplay" label="壓力等級" />
        <StatCard :value="perfDetail.worker_memory_guard.warn_count" label="警告次數" />
        <StatCard :value="perfDetail.worker_memory_guard.evict_count" label="驅逐次數" />
        <StatCard :value="perfDetail.worker_memory_guard.restart_count" label="重啟次數" />
      </div>
    </section>

    <!-- Storage Management -->
    <section class="panel" v-if="storageInfo">
      <h2 class="panel-title">儲存空間管理</h2>
      <p class="storage-total">總使用量：{{ formatBytes(storageInfo.total_bytes) }}</p>

      <div class="storage-section">
        <h4>SQLite 資料庫</h4>
        <table class="mini-table">
          <thead><tr><th>檔案</th><th>大小</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="f in storageInfo.sqlite_files" :key="f.path">
              <td>{{ f.path }}</td>
              <td>{{ formatBytes(f.size_bytes) }}</td>
              <td>
                <button
                  v-if="f.path.includes('metrics_history')"
                  class="btn btn-sm btn-danger"
                  :disabled="storagePurging"
                  @click="purgeMetricsHistory"
                >清除快照</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="storage-section">
        <h4>Log 檔案</h4>
        <table class="mini-table">
          <thead><tr><th>檔案</th><th>大小</th></tr></thead>
          <tbody>
            <tr v-for="f in storageInfo.log_files" :key="f.path">
              <td>{{ f.path }}</td>
              <td>{{ formatBytes(f.size_bytes) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="storage-section" v-if="storageInfo.archive_files?.length">
        <h4>Archive ({{ storageInfo.archive_files.length }} 檔, {{ formatBytes(storageInfo.archive_total_bytes) }})</h4>
        <table class="mini-table">
          <thead><tr><th>檔案</th><th>大小</th></tr></thead>
          <tbody>
            <tr v-for="f in storageInfo.archive_files" :key="f.path">
              <td>{{ f.path }}</td>
              <td>{{ formatBytes(f.size_bytes) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="storage-actions">
        <button class="btn btn-sm" :disabled="storagePurging" @click="cleanupLogFiles(['logs'])">
          {{ storagePurging ? '清理中...' : '清空 Log 檔案' }}
        </button>
        <button
          class="btn btn-sm"
          :disabled="storagePurging || !storageInfo.archive_files?.length"
          @click="cleanupLogFiles(['archive'])"
        >清空 Archive</button>
        <button class="btn btn-sm btn-danger" :disabled="storagePurging" @click="cleanupLogFiles(['logs', 'archive'])">
          全部清理
        </button>
      </div>
    </section>

    <!-- Worker Control -->
    <section class="panel">
      <h2 class="panel-title">Worker 控制</h2>
      <div class="worker-info">
        <StatCard :value="workerData?.worker_pid" label="PID" />
        <StatCard :value="workerStartTimeDisplay" label="啟動時間" />
        <StatCard :value="cooldownDisplay" label="冷卻狀態" />
      </div>
      <button
        class="btn btn-danger"
        :disabled="workerCooldownActive"
        @click="showRestartModal = true"
      >
        重啟 Worker
      </button>

      <!-- Restart Modal -->
      <div class="modal-backdrop" v-if="showRestartModal" @click.self="showRestartModal = false">
        <div class="modal-dialog">
          <h3>確認重啟 Worker</h3>
          <p>重啟將導致目前的請求暫時中斷，確定要繼續嗎？</p>
          <div class="modal-actions">
            <button class="btn" @click="showRestartModal = false">取消</button>
            <button class="btn btn-danger" @click="doRestart" :disabled="restartLoading">
              {{ restartLoading ? '重啟中...' : '確認重啟' }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- System Logs -->
    <section class="panel">
      <h2 class="panel-title">系統日誌</h2>
      <div class="log-controls">
        <select v-model="logLevel" @change="loadLogs">
          <option value="">全部等級</option>
          <option value="ERROR">ERROR</option>
          <option value="WARNING">WARNING</option>
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
        </select>
        <input
          type="text"
          v-model="logSearch"
          placeholder="搜尋日誌..."
          @input="debouncedLoadLogs"
        />
        <button class="btn btn-sm" @click="cleanupLogs" :disabled="cleanupLoading">
          {{ cleanupLoading ? '清理中...' : '清理日誌' }}
        </button>
      </div>
      <div class="log-table-wrapper">
        <table class="log-table" v-if="logsData?.logs?.length">
          <thead>
            <tr>
              <th>時間</th>
              <th>等級</th>
              <th>訊息</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(log, i) in logsData.logs" :key="i" :class="'log-' + (log.level || '').toLowerCase()">
              <td class="log-time">{{ log.timestamp }}</td>
              <td class="log-level">{{ log.level }}</td>
              <td class="log-msg">{{ log.message }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">無日誌</p>
      </div>
      <div class="log-pagination" v-if="logsData?.total > logLimit">
        <button class="btn btn-sm" :disabled="logOffset === 0" @click="logOffset -= logLimit; loadLogs()">上一頁</button>
        <span>{{ logOffset / logLimit + 1 }} / {{ Math.ceil(logsData.total / logLimit) }}</span>
        <button class="btn btn-sm" :disabled="logOffset + logLimit >= logsData.total" @click="logOffset += logLimit; loadLogs()">下一頁</button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { apiGet, apiPost } from '../core/api.js';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';

import GaugeBar from './components/GaugeBar.vue';
import StatCard from './components/StatCard.vue';
import StatusDot from './components/StatusDot.vue';
import TrendChart from './components/TrendChart.vue';

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

// --- State ---
const loading = ref(false);
const autoRefreshEnabled = ref(true);
const systemData = ref(null);
const metricsData = ref(null);
const perfDetail = ref(null);
const historyData = ref([]);
const logsData = ref(null);
const workerData = ref(null);

const logLevel = ref('');
const logSearch = ref('');
const logOffset = ref(0);
const logLimit = 50;

const showRestartModal = ref(false);
const restartLoading = ref(false);
const cleanupLoading = ref(false);
const storageInfo = ref(null);
const storagePurging = ref(false);

const latencyChartRef = ref(null);
let chartInstance = null;

// --- Computed ---
const dbStatus = computed(() => {
  const s = systemData.value?.database?.status;
  if (s === 'healthy' || s === 'ok') return 'healthy';
  if (s === 'error') return 'error';
  return 'disabled';
});
const dbStatusLabel = computed(() => systemData.value?.database?.status || '-');

const redisStatus = computed(() => {
  const r = systemData.value?.redis;
  if (!r?.enabled) return 'disabled';
  if (r.status === 'healthy' || r.status === 'ok') return 'healthy';
  if (r.status === 'error') return 'error';
  return 'degraded';
});
const redisStatusLabel = computed(() => {
  const r = systemData.value?.redis;
  if (!r?.enabled) return '未啟用';
  return r.status || '-';
});

const cbStatus = computed(() => {
  const s = systemData.value?.circuit_breaker?.state;
  if (s === 'CLOSED') return 'healthy';
  if (s === 'OPEN') return 'error';
  if (s === 'HALF_OPEN') return 'degraded';
  return 'disabled';
});
const cbStatusLabel = computed(() => systemData.value?.circuit_breaker?.state || '-');

const slowRateDisplay = computed(() => {
  const r = metricsData.value?.slow_rate;
  return r != null ? `${(r * 100).toFixed(1)}%` : '-';
});

const redisMemoryRatio = computed(() => {
  const r = perfDetail.value?.redis;
  if (!r) return 0;
  const used = r.used_memory || 0;
  const max = r.maxmemory || 0;
  if (max > 0) return used / max;
  const peak = r.peak_memory || used;
  return peak > 0 ? used / peak : 0;
});
const redisMemoryLabel = computed(() => {
  const r = perfDetail.value?.redis;
  if (!r) return '';
  const used = r.used_memory_human || 'N/A';
  const max = r.maxmemory && r.maxmemory > 0
    ? r.maxmemory_human
    : r.peak_memory_human;
  return `${used} / ${max || 'N/A'}`;
});

const hitRateDisplay = computed(() => {
  const r = perfDetail.value?.redis?.hit_rate;
  return r != null ? `${(r * 100).toFixed(1)}%` : '-';
});

const routeCacheL1HitRate = computed(() => {
  const r = perfDetail.value?.route_cache?.l1_hit_rate;
  return r != null ? `${(r * 100).toFixed(1)}%` : '-';
});
const routeCacheL2HitRate = computed(() => {
  const r = perfDetail.value?.route_cache?.l2_hit_rate;
  return r != null ? `${(r * 100).toFixed(1)}%` : '-';
});
const routeCacheMissRate = computed(() => {
  const r = perfDetail.value?.route_cache?.miss_rate;
  return r != null ? `${(r * 100).toFixed(1)}%` : '-';
});

const poolOverflowDisplay = computed(() => {
  const overflow = perfDetail.value?.db_pool?.status?.overflow;
  if (overflow == null) return '-';
  return Math.max(0, overflow);
});
const poolTotalConnections = computed(() => {
  const s = perfDetail.value?.db_pool?.status;
  if (!s) return '-';
  return (s.checked_out || 0) + (s.checked_in || 0);
});

const workerStartTimeDisplay = computed(() => {
  const t = workerData.value?.worker_start_time;
  if (!t) return '-';
  try {
    return new Date(t).toLocaleString('zh-TW');
  } catch {
    return t;
  }
});

const workerCooldownActive = computed(() => workerData.value?.cooldown?.active || false);
const cooldownDisplay = computed(() => {
  if (workerCooldownActive.value) {
    const secs = workerData.value?.cooldown?.remaining_seconds || 0;
    return `冷卻中 (${secs}s)`;
  }
  return '就緒';
});

const memoryGuardRssDisplay = computed(() => {
  const g = perfDetail.value?.worker_memory_guard;
  if (!g) return '';
  return `${g.last_rss_mb?.toFixed(1) ?? '-'} MB / ${g.limit_mb} MB (${g.rss_pct?.toFixed(1) ?? '-'}%)`;
});

const memoryGuardLevelDisplay = computed(() => {
  const level = perfDetail.value?.worker_memory_guard?.level;
  const levelMap = { normal: '正常', warn: '警告', evict: '驅逐中', restart: '重啟中' };
  return levelMap[level] || level || '-';
});

const paretoHitRateDisplay = computed(() => {
  const r = perfDetail.value?.pareto_materialization?.hit_rate;
  return r != null ? `${(r * 100).toFixed(1)}%` : '-';
});

const paretoBuildLatencyDisplay = computed(() => {
  const s = perfDetail.value?.pareto_materialization?.last_build_latency_s;
  return s != null ? `${s.toFixed(2)}s` : '-';
});

const paretoPayloadDisplay = computed(() => {
  const b = perfDetail.value?.pareto_materialization?.last_snapshot_payload_bytes;
  if (b == null) return '-';
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
});

const paretoFallbackReasons = computed(() => {
  const reasons = perfDetail.value?.pareto_materialization?.fallback_reasons;
  if (!reasons || typeof reasons !== 'object') return [];
  return Object.entries(reasons)
    .filter(([, count]) => count > 0)
    .map(([reason, count]) => ({ reason, count }));
});

// --- Data Fetching ---
async function loadSystemStatus() {
  try {
    const res = await apiGet('/admin/api/system-status');
    systemData.value = res?.data || null;
  } catch (e) {
    console.error('Failed to load system status:', e);
  }
}

async function loadMetrics() {
  try {
    const res = await apiGet('/admin/api/metrics');
    metricsData.value = res?.data || null;
    updateLatencyChart();
  } catch (e) {
    console.error('Failed to load metrics:', e);
  }
}

async function loadPerformanceDetail() {
  try {
    const res = await apiGet('/admin/api/performance-detail');
    perfDetail.value = res?.data || null;
  } catch (e) {
    console.error('Failed to load performance detail:', e);
  }
}

async function loadLogs() {
  try {
    const params = { limit: logLimit, offset: logOffset.value };
    if (logLevel.value) params.level = logLevel.value;
    if (logSearch.value) params.q = logSearch.value;
    const res = await apiGet('/admin/api/logs', { params });
    logsData.value = res?.data || null;
  } catch (e) {
    console.error('Failed to load logs:', e);
  }
}

async function loadWorkerStatus() {
  try {
    const res = await apiGet('/admin/api/worker/status');
    workerData.value = res?.data || null;
  } catch (e) {
    console.error('Failed to load worker status:', e);
  }
}

async function loadPerformanceHistory() {
  try {
    const res = await apiGet('/admin/api/performance-history', { params: { minutes: 30 } });
    const snapshots = res?.data?.snapshots || [];
    // Pre-process: convert worker_rss_bytes to worker_rss_mb for trend chart
    historyData.value = snapshots.map((s) => ({
      ...s,
      worker_rss_mb: s.worker_rss_bytes ? Math.round(s.worker_rss_bytes / 1048576 * 10) / 10 : 0,
      redis_used_memory_mb: s.redis_used_memory_mb ?? (s.redis_used_memory ? Math.round(s.redis_used_memory / 1048576 * 10) / 10 : 0),
    }));
  } catch (e) {
    console.error('Failed to load performance history:', e);
  }
}

async function loadStorageInfo() {
  try {
    const res = await apiGet('/admin/api/storage-info');
    storageInfo.value = res?.data || null;
  } catch (e) {
    console.error('Failed to load storage info:', e);
  }
}

async function purgeMetricsHistory() {
  if (!confirm('確定要清除所有效能快照資料？清除後趨勢圖將重新累積。')) return;
  storagePurging.value = true;
  try {
    await apiPost('/admin/api/performance-history/purge', {});
    await Promise.all([loadStorageInfo(), loadPerformanceHistory()]);
  } catch (e) {
    console.error('Failed to purge metrics history:', e);
  } finally {
    storagePurging.value = false;
  }
}

async function cleanupLogFiles(targets) {
  const label = targets.includes('logs') && targets.includes('archive') ? '所有 Log 和 Archive'
    : targets.includes('archive') ? 'Archive 目錄' : 'Log 檔案';
  if (!confirm(`確定要清理${label}？`)) return;
  storagePurging.value = true;
  try {
    await apiPost('/admin/api/log-files/cleanup', { targets });
    await loadStorageInfo();
  } catch (e) {
    console.error('Failed to cleanup log files:', e);
  } finally {
    storagePurging.value = false;
  }
}

function formatBytes(bytes) {
  if (bytes == null || bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
  return `${(bytes / 1073741824).toFixed(2)} GB`;
}

// --- Trend Chart Series Configs ---
const poolTrendSeries = [
  { name: '飽和度', key: 'pool_saturation', color: '#6366f1' },
  { name: '使用中', key: 'pool_checked_out', color: '#f59e0b' },
  { name: '慢查詢執行中', key: 'slow_query_active', color: '#ef4444' },
];

const latencyTrendSeries = [
  { name: 'P50', key: 'latency_p50_ms', color: '#22c55e' },
  { name: 'P95', key: 'latency_p95_ms', color: '#f59e0b' },
  { name: 'P99', key: 'latency_p99_ms', color: '#ef4444' },
];

const redisTrendSeries = [
  { name: '記憶體 (MB)', key: 'redis_used_memory_mb', color: '#06b6d4' },
];

const hitRateTrendSeries = [
  { name: 'Redis 命中率', key: 'redis_hit_rate', color: '#22c55e' },
  { name: 'L1 命中率', key: 'rc_l1_hit_rate', color: '#2563eb' },
  { name: 'L2 命中率', key: 'rc_l2_hit_rate', color: '#f59e0b' },
];

const memoryTrendSeries = [
  { name: 'RSS (MB)', key: 'worker_rss_mb', color: '#8b5cf6' },
];

async function refreshAll() {
  loading.value = true;
  try {
    await Promise.all([
      loadSystemStatus(),
      loadMetrics(),
      loadPerformanceDetail(),
      loadPerformanceHistory(),
      loadLogs(),
      loadWorkerStatus(),
      loadStorageInfo(),
    ]);
  } finally {
    loading.value = false;
  }
}

// --- Auto Refresh ---
const { startAutoRefresh, stopAutoRefresh } = useAutoRefresh({
  onRefresh: refreshAll,
  intervalMs: 30_000,
  autoStart: false,
});

function toggleAutoRefresh() {
  if (autoRefreshEnabled.value) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
}

// --- Worker Restart ---
async function doRestart() {
  restartLoading.value = true;
  try {
    await apiPost('/admin/api/worker/restart', {});
    showRestartModal.value = false;
    await loadWorkerStatus();
  } catch (e) {
    alert(e.message || '重啟失敗');
  } finally {
    restartLoading.value = false;
  }
}

// --- Log Cleanup ---
async function cleanupLogs() {
  cleanupLoading.value = true;
  try {
    await apiPost('/admin/api/logs/cleanup', {});
    await loadLogs();
  } catch (e) {
    console.error('Failed to cleanup logs:', e);
  } finally {
    cleanupLoading.value = false;
  }
}

// --- Debounce ---
let debounceTimer = null;
function debouncedLoadLogs() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    logOffset.value = 0;
    loadLogs();
  }, 300);
}

// --- ECharts ---
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

  // Build histogram buckets
  const buckets = [
    { label: '<100ms', max: 100 },
    { label: '100-500ms', max: 500 },
    { label: '500ms-1s', max: 1000 },
    { label: '1-5s', max: 5000 },
    { label: '>5s', max: Infinity },
  ];
  const counts = buckets.map(() => 0);
  for (const ms of latencies.map((v) => v * 1000)) {
    for (let i = 0; i < buckets.length; i++) {
      if (ms < buckets[i].max || i === buckets.length - 1) {
        counts[i]++;
        break;
      }
    }
  }

  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: buckets.map((b) => b.label) },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar',
        data: counts,
        itemStyle: { color: '#6366f1' },
        barMaxWidth: 40,
      },
    ],
  });
}

// --- Lifecycle ---
onMounted(async () => {
  await refreshAll();
  if (autoRefreshEnabled.value) {
    startAutoRefresh();
  }
});

onBeforeUnmount(() => {
  stopAutoRefresh();
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
  clearTimeout(debounceTimer);
});
</script>
