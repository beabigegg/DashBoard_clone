<script setup>
import { computed, onMounted, ref } from 'vue';

import { apiGet, apiPost } from '../../core/api.js';
import GaugeBar from '../../admin-shared/components/GaugeBar.vue';
import StatCard from '../../admin-shared/components/StatCard.vue';
import StatusDot from '../../admin-shared/components/StatusDot.vue';
import TrendChart from '../../admin-shared/components/TrendChart.vue';
import {
  usePerfDetail,
  usePerfHistory,
  useStorageInfo,
} from '../../admin-shared/composables/useAdminData.js';

const perfDetailHook = usePerfDetail();
const historyHook = usePerfHistory(30, 30);
const storageHook = useStorageInfo();

const workerData = ref(null);
const workerStatusError = ref('');
const restartLoading = ref(false);
const showRestartModal = ref(false);
const storagePurging = ref(false);

const perfDetail = computed(() => perfDetailHook.data.value || null);
const historyData = computed(() => historyHook.data.value || []);
const storageInfo = computed(() => storageHook.data.value || null);

const errorMessage = computed(
  () => perfDetailHook.error.value
    || historyHook.error.value
    || storageHook.error.value
    || workerStatusError.value
    || '',
);

const memoryGuardRssDisplay = computed(() => {
  const guard = perfDetail.value?.worker_memory_guard;
  if (!guard) return '';
  return `${guard.last_rss_mb?.toFixed(1) ?? '-'} MB / ${guard.limit_mb} MB (${guard.rss_pct?.toFixed(1) ?? '-'}%)`;
});

const memoryGuardLevelDisplay = computed(() => {
  const level = perfDetail.value?.worker_memory_guard?.level;
  const map = { normal: '正常', warn: '警告', evict: '驅逐中', restart: '重啟中' };
  return map[level] || level || '-';
});

const asyncWorkers = computed(() => perfDetail.value?.async_workers || {});
const rqWorkers = computed(() => asyncWorkers.value.workers?.workers || []);
const rqQueues = computed(() => asyncWorkers.value.queues?.queues || []);
const heavyQuerySlots = computed(() => asyncWorkers.value.slots || null);

const workerStartTimeDisplay = computed(() => {
  const value = workerData.value?.worker_start_time;
  if (!value) return '-';
  try {
    return new Date(value).toLocaleString('zh-TW');
  } catch {
    return value;
  }
});

const workerCooldownActive = computed(() => workerData.value?.cooldown?.active || false);
const cooldownDisplay = computed(() => {
  if (workerCooldownActive.value) {
    const seconds = workerData.value?.cooldown?.remaining_seconds || 0;
    return `冷卻中 (${seconds}s)`;
  }
  return '就緒';
});

const memoryTrendSeries = [
  { name: 'RSS (MB)', key: 'worker_rss_mb', color: 'rgb(139, 92, 246)' },
];

const asyncWorkerTrendSeries = [
  { name: '忙碌 Workers', key: 'rq_workers_busy', color: 'rgb(245, 158, 11)' },
  { name: '總 Workers', key: 'rq_workers_total', color: 'rgb(34, 197, 94)' },
];

const asyncQueueTrendSeries = [
  { name: '佇列深度', key: 'rq_queue_depth', color: 'rgb(99, 102, 241)' },
  { name: '並行槽位', key: 'heavy_query_slots_active', color: 'rgb(239, 68, 68)' },
];

function workerStateColor(state) {
  if (state === 'busy') return 'amber';
  if (state === 'idle') return 'green';
  return 'gray';
}

function formatUptime(birthDate) {
  if (!birthDate) return '-';
  try {
    const diffMs = Date.now() - new Date(birthDate).getTime();
    if (Number.isNaN(diffMs) || diffMs < 0) return '-';
    const totalSeconds = Math.floor(diffMs / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (days > 0) return `${days}d ${hours}h`;
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  } catch {
    return '-';
  }
}

function formatBytes(bytes) {
  if (bytes == null || bytes === 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1073741824) return `${(bytes / 1048576).toFixed(1)} MB`;
  return `${(bytes / 1073741824).toFixed(2)} GB`;
}

async function loadWorkerStatus() {
  workerStatusError.value = '';
  try {
    const response = await apiGet('/admin/api/worker/status');
    workerData.value = response?.data || null;
  } catch (error) {
    workerStatusError.value = error.message || '載入 Worker 狀態失敗';
  }
}

async function doRestart() {
  restartLoading.value = true;
  try {
    await apiPost('/admin/api/worker/restart', {});
    showRestartModal.value = false;
    await loadWorkerStatus();
  } catch (error) {
    window.alert(error.message || '重啟失敗');
  } finally {
    restartLoading.value = false;
  }
}

async function purgeMetricsHistory() {
  if (!window.confirm('確定要清除所有效能快照資料？清除後趨勢圖將重新累積。')) {
    return;
  }
  storagePurging.value = true;
  try {
    await apiPost('/admin/api/performance-history/purge', {});
    await Promise.all([storageHook.refresh(), historyHook.refresh()]);
  } finally {
    storagePurging.value = false;
  }
}

async function cleanupLogFiles(targets) {
  const label = targets.includes('logs') && targets.includes('archive')
    ? '所有 Log 和 Archive'
    : targets.includes('archive')
      ? 'Archive 目錄'
      : 'Log 檔案';
  if (!window.confirm(`確定要清理${label}？`)) {
    return;
  }
  storagePurging.value = true;
  try {
    await apiPost('/admin/api/log-files/cleanup', { targets });
    await storageHook.refresh();
  } finally {
    storagePurging.value = false;
  }
}

async function refresh() {
  await Promise.all([
    perfDetailHook.refresh(),
    historyHook.refresh(),
    storageHook.refresh(),
    loadWorkerStatus(),
  ]);
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="worker-tab">
    <section v-if="errorMessage" class="panel panel-disabled">
      <div class="muted">{{ errorMessage }}</div>
    </section>

    <TrendChart
      v-if="historyData.length > 1"
      title="Worker 記憶體趨勢"
      :snapshots="historyData"
      :series="memoryTrendSeries"
      yAxisLabel="MB"
    />

    <section class="panel" v-if="perfDetail?.worker_memory_guard?.enabled">
      <h2 class="panel-title">Worker 記憶體守衛</h2>
      <GaugeBar
        label="RSS 使用率"
        :value="perfDetail.worker_memory_guard.rss_pct"
        :max="100"
        unit="%"
        :displayText="memoryGuardRssDisplay"
        :warningThreshold="0.7"
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

    <section
      class="panel"
      v-if="perfDetail?.async_workers && !perfDetail.async_workers.error"
    >
      <h2 class="panel-title">非同步查詢 Worker</h2>

      <div class="status-cards-grid">
        <div class="status-card">
          <div class="status-card-title">RQ 可用性</div>
          <StatusDot
            :status="asyncWorkers.rq_available ? 'healthy' : 'error'"
            :label="asyncWorkers.rq_available ? '可用' : '不可用'"
          />
        </div>
        <div class="status-card">
          <div class="status-card-title">Worker 占用</div>
          <StatusDot
            :status="asyncWorkers.workers?.summary?.busy > 0 ? 'degraded' : 'healthy'"
            :label="`${asyncWorkers.workers?.summary?.busy ?? 0}/${asyncWorkers.workers?.summary?.total ?? 0} 忙碌`"
          />
        </div>
        <div class="status-card">
          <div class="status-card-title">佇列排隊</div>
          <StatCard :value="asyncWorkers.queues?.total_queued ?? 0" label="" />
        </div>
        <div class="status-card">
          <div class="status-card-title">失敗任務</div>
          <StatCard :value="asyncWorkers.queues?.total_failed ?? 0" label="" />
        </div>
      </div>

      <GaugeBar
        v-if="heavyQuerySlots"
        label="Heavy Query 並行槽位"
        :value="heavyQuerySlots.active"
        :max="heavyQuerySlots.max"
        :displayText="`${heavyQuerySlots.active} / ${heavyQuerySlots.max} (${heavyQuerySlots.utilization_pct?.toFixed(1) ?? 0}%)`"
        :warningThreshold="0.6"
        :dangerThreshold="0.85"
      />

      <h3 class="sub-title">Worker 狀態</h3>
      <table class="mini-table" v-if="rqWorkers.length">
        <thead>
          <tr>
            <th>名稱</th>
            <th>狀態</th>
            <th>目前任務</th>
            <th>佇列</th>
            <th>成功</th>
            <th>失敗</th>
            <th>已運行</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="worker in rqWorkers" :key="worker.name">
            <td>{{ worker.name }}</td>
            <td>
              <span class="rq-worker-state-dot" :class="`rq-worker-state-dot--${workerStateColor(worker.state)}`"></span>
              {{ worker.state }}
            </td>
            <td class="rq-job-id">{{ worker.current_job || '-' }}</td>
            <td>{{ worker.queues?.join(', ') || '-' }}</td>
            <td>{{ worker.successful_job_count ?? 0 }}</td>
            <td>{{ worker.failed_job_count ?? 0 }}</td>
            <td>{{ formatUptime(worker.birth_date) }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted" v-else>無活躍 Worker</p>

      <h3 class="sub-title">佇列狀態</h3>
      <table class="mini-table" v-if="rqQueues.length">
        <thead>
          <tr>
            <th>佇列名稱</th>
            <th>排隊深度</th>
            <th>執行中</th>
            <th>失敗</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="queue in rqQueues" :key="queue.name">
            <td>{{ queue.name }}</td>
            <td>{{ queue.depth ?? 0 }}</td>
            <td>{{ queue.started ?? 0 }}</td>
            <td>{{ queue.failed ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
      <p class="muted" v-else>無佇列資料</p>
    </section>
    <section class="panel panel-disabled" v-else-if="perfDetail && perfDetail.async_workers?.error">
      <h2 class="panel-title">非同步查詢 Worker</h2>
      <p class="muted">RQ Worker 監控不可用：{{ perfDetail.async_workers.error }}</p>
    </section>
    <section class="panel panel-disabled" v-else-if="perfDetail && !perfDetail.async_workers">
      <h2 class="panel-title">非同步查詢 Worker</h2>
      <p class="muted">RQ Worker 監控不可用</p>
    </section>

    <TrendChart
      v-if="historyData.length > 1"
      title="非同步 Worker 趨勢"
      :snapshots="historyData"
      :series="asyncWorkerTrendSeries"
    />

    <TrendChart
      v-if="historyData.length > 1"
      title="佇列深度 & 槽位趨勢"
      :snapshots="historyData"
      :series="asyncQueueTrendSeries"
    />

    <section class="panel" v-if="storageInfo">
      <h2 class="panel-title">儲存空間管理</h2>
      <p class="storage-total">總使用量：{{ formatBytes(storageInfo.total_bytes) }}</p>

      <div class="storage-section">
        <h4>SQLite 資料庫</h4>
        <table class="mini-table">
          <thead><tr><th>檔案</th><th>大小</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="file in storageInfo.sqlite_files" :key="file.path">
              <td>{{ file.path }}</td>
              <td>{{ formatBytes(file.size_bytes) }}</td>
              <td>
                <button
                  v-if="file.path.includes('metrics_history')"
                  class="ui-btn ui-btn--danger ui-btn--sm"
                  :disabled="storagePurging"
                  @click="purgeMetricsHistory"
                >
                  清除快照
                </button>
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
            <tr v-for="file in storageInfo.log_files" :key="file.path">
              <td>{{ file.path }}</td>
              <td>{{ formatBytes(file.size_bytes) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="storage-section" v-if="storageInfo.archive_files?.length">
        <h4>Archive ({{ storageInfo.archive_files.length }} 檔, {{ formatBytes(storageInfo.archive_total_bytes) }})</h4>
        <table class="mini-table">
          <thead><tr><th>檔案</th><th>大小</th></tr></thead>
          <tbody>
            <tr v-for="file in storageInfo.archive_files" :key="file.path">
              <td>{{ file.path }}</td>
              <td>{{ formatBytes(file.size_bytes) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="storage-actions">
        <button class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="storagePurging" @click="cleanupLogFiles(['logs'])">
          {{ storagePurging ? '清理中...' : '清空 Log 檔案' }}
        </button>
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :disabled="storagePurging || !storageInfo.archive_files?.length"
          @click="cleanupLogFiles(['archive'])"
        >
          清空 Archive
        </button>
        <button class="ui-btn ui-btn--danger ui-btn--sm" :disabled="storagePurging" @click="cleanupLogFiles(['logs', 'archive'])">
          全部清理
        </button>
      </div>
    </section>

    <section class="panel">
      <h2 class="panel-title">Worker 控制</h2>
      <div class="worker-info">
        <StatCard :value="workerData?.worker_pid" label="PID" />
        <StatCard :value="workerStartTimeDisplay" label="啟動時間" />
        <StatCard :value="cooldownDisplay" label="冷卻狀態" />
      </div>
      <button
        class="ui-btn ui-btn--danger"
        :disabled="workerCooldownActive"
        @click="showRestartModal = true"
      >
        重啟 Worker
      </button>

      <div class="modal-backdrop" v-if="showRestartModal" @click.self="showRestartModal = false">
        <div class="modal-dialog">
          <h3>確認重啟 Worker</h3>
          <p>重啟將導致目前的請求暫時中斷，確定要繼續嗎？</p>
          <div class="modal-actions">
            <button class="ui-btn ui-btn--ghost" @click="showRestartModal = false">取消</button>
            <button class="ui-btn ui-btn--danger" @click="doRestart" :disabled="restartLoading">
              {{ restartLoading ? '重啟中...' : '確認重啟' }}
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
