<script setup>
import { computed, onMounted, ref } from 'vue';

import { apiGet, apiPost } from '../../core/api.js';
import { formatLogTime } from '../../core/datetime.js';
import GaugeBar from '../../admin-shared/components/GaugeBar.vue';
import StatCard from '../../admin-shared/components/StatCard.vue';
import StatusDot from '../../admin-shared/components/StatusDot.vue';
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
} from '../../admin-shared/composables/useAdminData';
import { useLastUpdated } from '../../admin-shared/composables/useLastUpdated';

const perfDetailHook = usePerfDetail();
const historyHook = usePerfHistory(30, 30);
const { lastUpdatedLabel, markUpdated } = useLastUpdated();

const workerData = ref(null);
const workerStatusError = ref('');
const restartLoading = ref(false);
const showRestartModal = ref(false);

const perfDetail = computed(() => perfDetailHook.data.value || null);
const historyData = computed(() => historyHook.data.value || []);

const errorMessage = computed(
  () => perfDetailHook.error.value
    || historyHook.error.value
    || workerStatusError.value
    || '',
);

const memoryGuardRssDisplay = computed(() => {
  const processMemory = perfDetail.value?.worker_memory_guard?.process_memory
    || perfDetail.value?.worker_memory_guard;
  if (!processMemory) return '';
  return `${processMemory.rss_mb?.toFixed?.(1) ?? processMemory.last_rss_mb?.toFixed?.(1) ?? '-'} MB / ${processMemory.limit_mb} MB (${processMemory.rss_pct?.toFixed(1) ?? '-'}%)`;
});

const memoryGuardLevelDisplay = computed(() => {
  const level = perfDetail.value?.worker_memory_guard?.process_memory?.level
    || perfDetail.value?.worker_memory_guard?.level;
  const map = { normal: '正常', warn: '警告', evict: '驅逐中', restart: '重啟中' };
  return map[level] || level || '-';
});

const systemMemory = computed(
  () => perfDetail.value?.worker_memory_guard?.system_memory || {},
);

const serviceMemory = computed(
  () => perfDetail.value?.worker_memory_guard?.service_memory || {},
);

const serviceMemoryDisplay = computed(() => {
  const info = serviceMemory.value || {};
  if (typeof info.rss_mb !== 'number') return '';
  return `${info.rss_mb.toFixed(1)} MB (${info.process_count ?? 0} processes)`;
});

const systemMemoryDisplay = computed(() => {
  const info = systemMemory.value || {};
  if (typeof info.used_pct !== 'number') return '';
  const used = typeof info.used_mb === 'number' ? info.used_mb : '-';
  const total = typeof info.total_mb === 'number' ? info.total_mb : '-';
  return `${info.used_pct.toFixed(1)}% (${used} MB / ${total} MB)`;
});

const systemMemoryLevelDisplay = computed(() => {
  const state = systemMemory.value?.pressure_state;
  const map = { normal: '正常', warning: '警告', critical: '危急' };
  return map[state] || state || '-';
});

const asyncWorkers = computed(() => perfDetail.value?.async_workers || {});
const rqWorkers = computed(() => asyncWorkers.value.workers?.workers || []);
const rqQueues = computed(() => asyncWorkers.value.queues?.queues || []);
const heavyQuerySlots = computed(() => asyncWorkers.value.slots || null);

const workerStartTimeDisplay = computed(() => formatLogTime(workerData.value?.worker_start_time));

const workerCooldownActive = computed(() => workerData.value?.cooldown?.active || false);
const cooldownDisplay = computed(() => {
  if (workerCooldownActive.value) {
    const seconds = workerData.value?.cooldown?.remaining_seconds || 0;
    return `冷卻中 (${seconds}s)`;
  }
  return '就緒';
});

const memoryTrendSeries = [
  { name: 'Process RSS (MB)', key: 'worker_rss_mb', color: 'rgb(139, 92, 246)' },
  { name: 'Server RSS (MB)', key: 'service_rss_mb', color: 'rgb(59, 130, 246)' },
];

const systemMemoryTrendSeries = [
  { name: 'System Used %', key: 'system_mem_used_pct', color: 'rgb(239, 68, 68)' },
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

async function refresh() {
  await Promise.all([
    perfDetailHook.refresh(),
    historyHook.refresh(),
    loadWorkerStatus(),
  ]);
  markUpdated();
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="worker-tab">
    <div class="admin-tab__last-updated" role="status" aria-live="polite">{{ lastUpdatedLabel }}</div>
    <ErrorBanner :message="errorMessage" :dismissible="false" data-testid="error-banner" />

    <SectionCard v-if="perfDetail?.worker_memory_guard?.enabled">
      <template #header><h2 class="panel-title">記憶體守衛</h2></template>
      <p class="muted">Process 看單一 worker；Server 看整個 mes-dashboard 服務總 RSS；System 看主機總記憶體使用率。</p>
      <h3 class="sub-title">Process 單一進程</h3>
      <GaugeBar
        label="RSS 使用率"
        :value="perfDetail.worker_memory_guard.process_memory?.rss_pct ?? perfDetail.worker_memory_guard.rss_pct"
        :max="100"
        unit="%"
        :displayText="memoryGuardRssDisplay"
        :warningThreshold="0.7"
        :dangerThreshold="0.85"
      />
      <SummaryCardGroup :columns="6">
        <SummaryCard label="當前 RSS (MB)" :value="perfDetail.worker_memory_guard.process_memory?.rss_mb?.toFixed(1) ?? perfDetail.worker_memory_guard.last_rss_mb?.toFixed(1)" accent="info" />
        <SummaryCard label="上限 (MB)" :value="perfDetail.worker_memory_guard.process_memory?.limit_mb ?? perfDetail.worker_memory_guard.limit_mb" accent="neutral" />
        <SummaryCard label="壓力等級" :value="memoryGuardLevelDisplay" accent="warning" />
        <SummaryCard label="警告次數" :value="perfDetail.worker_memory_guard.process_memory?.warn_count ?? perfDetail.worker_memory_guard.warn_count" accent="warning" />
        <SummaryCard label="驅逐次數" :value="perfDetail.worker_memory_guard.process_memory?.evict_count ?? perfDetail.worker_memory_guard.evict_count" accent="danger" />
        <SummaryCard label="重啟次數" :value="perfDetail.worker_memory_guard.process_memory?.restart_count ?? perfDetail.worker_memory_guard.restart_count" accent="danger" />
      </SummaryCardGroup>

      <h3 class="sub-title">Server 整個服務</h3>
      <SummaryCardGroup :columns="5">
        <SummaryCard label="總 RSS (MB)" :value="serviceMemory.rss_mb?.toFixed(1)" accent="info" />
        <SummaryCard label="監控進程數" :value="serviceMemory.process_count" accent="neutral" />
        <SummaryCard label="Gunicorn RSS (MB)" :value="serviceMemory.gunicorn_rss_mb?.toFixed(1)" accent="info" />
        <SummaryCard label="RQ RSS (MB)" :value="serviceMemory.rq_rss_mb?.toFixed(1)" accent="warning" />
        <SummaryCard label="Server 摘要" :value="serviceMemoryDisplay" accent="neutral" />
      </SummaryCardGroup>

      <h3 class="sub-title">System 全機</h3>
      <GaugeBar
        label="總記憶體使用率"
        :value="systemMemory.used_pct || 0"
        :max="100"
        unit="%"
        :displayText="systemMemoryDisplay"
        :warningThreshold="0.85"
        :dangerThreshold="0.92"
      />
      <SummaryCardGroup :columns="6">
        <SummaryCard label="壓力狀態" :value="systemMemoryLevelDisplay" accent="warning" />
        <SummaryCard label="已使用 (MB)" :value="systemMemory.used_mb" accent="danger" />
        <SummaryCard label="可用 (MB)" :value="systemMemory.available_mb" accent="info" />
        <SummaryCard label="總量 (MB)" :value="systemMemory.total_mb" accent="neutral" />
        <SummaryCard label="警告門檻 (%)" :value="systemMemory.warn_threshold_pct" accent="warning" />
        <SummaryCard label="拒絕門檻 (%)" :value="systemMemory.reject_threshold_pct" accent="danger" />
      </SummaryCardGroup>
    </SectionCard>

    <SectionCard
      v-if="perfDetail?.async_workers && !perfDetail.async_workers.error"
    >
      <template #header><h2 class="panel-title">非同步查詢 Worker</h2></template>

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
      <DataTable v-if="rqWorkers.length" :data="rqWorkers">
        <DataTableColumn columnKey="name" label="名稱" />
        <DataTableColumn columnKey="state" label="狀態" />
        <DataTableColumn columnKey="current_job" label="目前任務" />
        <DataTableColumn columnKey="queues" label="佇列" />
        <DataTableColumn columnKey="successful_job_count" label="成功" align="right" />
        <DataTableColumn columnKey="failed_job_count" label="失敗" align="right" />
        <DataTableColumn columnKey="birth_date" label="已運行" />
        <template #cell="{ row, columnKey, value }">
          <template v-if="columnKey === 'state'">
            <span class="rq-worker-state-dot" :class="`rq-worker-state-dot--${workerStateColor(row.state)}`"></span>
            {{ row.state }}
          </template>
          <template v-else-if="columnKey === 'current_job'">
            <span class="rq-job-id">{{ row.current_job || '-' }}</span>
          </template>
          <template v-else-if="columnKey === 'queues'">
            {{ row.queues?.join(', ') || '-' }}
          </template>
          <template v-else-if="columnKey === 'successful_job_count'">
            {{ row.successful_job_count ?? 0 }}
          </template>
          <template v-else-if="columnKey === 'failed_job_count'">
            {{ row.failed_job_count ?? 0 }}
          </template>
          <template v-else-if="columnKey === 'birth_date'">
            {{ formatUptime(row.birth_date) }}
          </template>
          <template v-else>{{ value }}</template>
        </template>
      </DataTable>
      <p class="muted" v-else>無活躍 Worker</p>

      <h3 class="sub-title">佇列狀態</h3>
      <DataTable v-if="rqQueues.length" :data="rqQueues">
        <DataTableColumn columnKey="name" label="佇列名稱" />
        <DataTableColumn columnKey="depth" label="排隊深度" align="right" />
        <DataTableColumn columnKey="started" label="執行中" align="right" />
        <DataTableColumn columnKey="failed" label="失敗" align="right" />
        <template #cell="{ row, columnKey, value }">
          <template v-if="columnKey === 'depth'">{{ row.depth ?? 0 }}</template>
          <template v-else-if="columnKey === 'started'">{{ row.started ?? 0 }}</template>
          <template v-else-if="columnKey === 'failed'">{{ row.failed ?? 0 }}</template>
          <template v-else>{{ value }}</template>
        </template>
      </DataTable>
      <p class="muted" v-else>無佇列資料</p>
    </SectionCard>
    <SectionCard v-else-if="perfDetail && perfDetail.async_workers?.error">
      <template #header><h2 class="panel-title">非同步查詢 Worker</h2></template>
      <p class="muted">RQ Worker 監控不可用：{{ perfDetail.async_workers.error }}</p>
    </SectionCard>
    <SectionCard v-else-if="perfDetail && !perfDetail.async_workers">
      <template #header><h2 class="panel-title">非同步查詢 Worker</h2></template>
      <p class="muted">RQ Worker 監控不可用</p>
    </SectionCard>

    <SectionCard>
      <template #header><h2 class="panel-title">Worker 控制</h2></template>
      <SummaryCardGroup :columns="3">
        <SummaryCard label="PID" :value="workerData?.worker_pid" accent="info" />
        <SummaryCard label="啟動時間" :value="workerStartTimeDisplay" accent="neutral" />
        <SummaryCard label="冷卻狀態" :value="cooldownDisplay" accent="brand" />
      </SummaryCardGroup>
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
    </SectionCard>

    <TrendChart
      title="Process / Server RSS 趨勢"
      :snapshots="historyData"
      :series="memoryTrendSeries"
      yAxisLabel="MB"
    />

    <TrendChart
      title="System 全機記憶體趨勢"
      :snapshots="historyData"
      :series="systemMemoryTrendSeries"
      yAxisLabel="%"
      :yMax="100"
    />

    <TrendChart
      title="非同步 Worker 趨勢"
      :snapshots="historyData"
      :series="asyncWorkerTrendSeries"
    />

    <TrendChart
      title="佇列深度 & 槽位趨勢"
      :snapshots="historyData"
      :series="asyncQueueTrendSeries"
    />
  </div>
</template>
