<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import {
  buildHealthFallbackDetail,
  labelFromHealthStatus,
  normalizeFrontendShellHealth,
} from '../healthSummary.js';

const status = ref('loading');
const label = ref('檢查中...');
const popupOpen = ref(false);
const healthData = ref(null);
const warnings = ref([]);
const frontendErrors = ref([]);

let timer = null;

const statusClass = computed(() => {
  if (status.value === 'healthy') return 'healthy';
  if (status.value === 'degraded') return 'degraded';
  if (status.value === 'loading') return 'loading';
  return 'unhealthy';
});

function toStatusText(raw) {
  if (raw === 'ok') return '正常';
  if (raw === 'disabled') return '未啟用';
  return '異常';
}

function formatDateTime(dateStr) {
  if (!dateStr) return '--';
  try {
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) return dateStr;
    return date.toLocaleString('zh-TW', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

function normalizeHitRate(value) {
  if (value == null || value === '') return '--';
  const n = parseFloat(value);
  if (Number.isNaN(n)) return String(value);
  return `${(n * 100).toFixed(0)}%`;
}

function toCircuitText(state) {
  if (!state || state === '-') return '--';
  if (state === 'CLOSED') return '🟢 CLOSED';
  if (state === 'OPEN') return '🔴 OPEN';
  if (state === 'HALF_OPEN') return '🟡 HALF_OPEN';
  return state;
}

function toPoolText(saturation) {
  if (saturation == null) return null;
  return `Pool ${(saturation * 100).toFixed(0)}%`;
}

const coreServices = computed(() => {
  const d = healthData.value;
  if (!d) return null;
  return {
    db: toStatusText(d.services?.database || 'error'),
    dbPool: toPoolText(d.database_pool?.state?.saturation),
    redis: toStatusText(d.services?.redis || 'disabled'),
    circuitBreaker: toCircuitText(d.circuit_breaker?.state),
  };
});

const systemResources = computed(() => {
  const d = healthData.value;
  if (!d) return null;
  const mem = d.system_memory || {};
  let memText = '--';
  if (typeof mem.used_pct === 'number') {
    const usedMb = typeof mem.total_mb === 'number' && typeof mem.available_mb === 'number'
      ? Math.max(0, mem.total_mb - mem.available_mb).toFixed(0)
      : null;
    memText = usedMb != null
      ? `${mem.used_pct.toFixed(1)}% (${usedMb}/${mem.total_mb?.toFixed(0)}MB)`
      : `${mem.used_pct.toFixed(1)}%`;
  }
  return {
    memory: memText,
    onlineCount: typeof d.online_count === 'number' ? d.online_count : null,
  };
});

const cacheInfo = computed(() => {
  const d = healthData.value;
  if (!d) return null;
  const rc = d.route_cache || {};
  const res = d.resource_cache || {};
  const wc = d.workcenter_mapping || {};
  return {
    wipEnabled: d.cache?.enabled ? '已啟用' : '未啟用',
    wipUpdatedAt: formatDateTime(d.cache?.updated_at),
    resourceStatus: res.enabled ? (res.loaded ? '已載入' : '未載入') : '未啟用',
    resourceCount: res.count != null ? `${res.count} 筆` : '--',
    routeMode: rc.mode || '--',
    routeHitRate: `${normalizeHitRate(rc.l1_hit_rate)} / ${normalizeHitRate(rc.l2_hit_rate)}`,
    workcenterCount: typeof wc.workcenter_count === 'number'
      ? `${wc.workcenter_count} wc / ${wc.group_count ?? '--'} groups`
      : '--',
  };
});

const bgServices = computed(() => {
  const d = healthData.value;
  if (!d) return null;
  const aw = d.async_workers || {};
  const ws = aw.workers?.summary || {};
  const qs = aw.queues || {};
  const sw = d.sync_worker || {};
  const as = d.anomaly_scheduler || {};
  return {
    rqWorkers: ws.total != null
      ? `${ws.busy ?? 0}/${ws.total} Queue: ${qs.total_queued ?? qs.total_depth ?? 0}`
      : '--',
    rqStatus: ws.total != null ? (ws.total > 0 ? 'ok' : 'error') : 'disabled',
    syncWorker: sw.running
      ? `🟢 last: ${formatDateTime(sw.last_sync_at)}`
      : (sw.running === false ? '⚫ 未啟用' : '--'),
    anomaly: as.running
      ? `🟢 ${as.anomaly_count ?? 0} anomalies`
      : (as.running === false ? '⚫ 未啟用' : '--'),
  };
});

function togglePopup() {
  popupOpen.value = !popupOpen.value;
}

function closePopup() {
  popupOpen.value = false;
}

function onDocumentClick(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest('#shellHealthWrap')) return;
  closePopup();
}

function onDocumentKeydown(event) {
  if (event.key === 'Escape') closePopup();
}

async function checkHealth() {
  try {
    const [healthResp, shellResp] = await Promise.all([
      fetch('/health', { cache: 'no-store' }),
      fetch('/health/frontend-shell', { cache: 'no-store' }),
    ]);

    if (!healthResp.ok) throw new Error(`Health API ${healthResp.status}`);

    const data = await healthResp.json();
    const shellData = shellResp.ok ? await shellResp.json() : null;

    status.value = data.status || 'unhealthy';
    label.value = labelFromHealthStatus(status.value);
    healthData.value = data;

    const frontendShell = normalizeFrontendShellHealth(shellData);
    warnings.value = Array.isArray(data.warnings) ? data.warnings : [];
    frontendErrors.value = frontendShell.errors;
  } catch {
    const fallback = buildHealthFallbackDetail();
    status.value = fallback.status;
    label.value = fallback.label;
    healthData.value = null;
    warnings.value = [];
    frontendErrors.value = [];
  }
}

onMounted(() => {
  void checkHealth();
  timer = window.setInterval(() => { void checkHealth(); }, 30000);
  document.addEventListener('click', onDocumentClick);
  document.addEventListener('keydown', onDocumentKeydown);
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
  document.removeEventListener('click', onDocumentClick);
  document.removeEventListener('keydown', onDocumentKeydown);
});
</script>

<template>
  <div id="shellHealthWrap" class="health-wrap">
    <button
      type="button"
      class="health-trigger"
      :aria-expanded="popupOpen ? 'true' : 'false'"
      aria-controls="shellHealthPopup"
      @click="togglePopup"
    >
      <span class="dot" :class="statusClass"></span>
      <span class="label">{{ label }}</span>
      <span class="meta-toggle">詳情</span>
    </button>

    <div v-if="popupOpen" id="shellHealthPopup" class="health-popup">
      <h4>系統連線狀態</h4>

      <!-- 核心服務 -->
      <div class="health-section-group">
        <div class="health-section-title">核心服務</div>
        <div class="health-item">
          <span class="health-item-label">資料庫 (Oracle)</span>
          <span class="health-item-value">
            {{ coreServices?.db }}
            <span v-if="coreServices?.dbPool" class="health-item-meta">{{ coreServices.dbPool }}</span>
          </span>
        </div>
        <div class="health-item">
          <span class="health-item-label">快取 (Redis)</span>
          <span class="health-item-value">{{ coreServices?.redis }}</span>
        </div>
        <div class="health-item">
          <span class="health-item-label">Circuit Breaker</span>
          <span class="health-item-value">{{ coreServices?.circuitBreaker }}</span>
        </div>
      </div>

      <!-- 系統資源 -->
      <div class="health-section-group">
        <div class="health-section-title">系統資源</div>
        <div class="health-item">
          <span class="health-item-label">記憶體</span>
          <span class="health-item-value">{{ systemResources?.memory }}</span>
        </div>
        <div v-if="systemResources?.onlineCount != null" class="health-item">
          <span class="health-item-label">在線人數</span>
          <span class="health-item-value">👤 {{ systemResources.onlineCount }}</span>
        </div>
      </div>

      <!-- 快取 -->
      <div class="health-section-group">
        <div class="health-section-title">快取</div>
        <div class="health-item">
          <span class="health-item-label">WIP 快取</span>
          <span class="health-item-value">{{ cacheInfo?.wipEnabled }} 同步 {{ cacheInfo?.wipUpdatedAt }}</span>
        </div>
        <div class="health-item">
          <span class="health-item-label">設備主檔</span>
          <span class="health-item-value">{{ cacheInfo?.resourceStatus }} {{ cacheInfo?.resourceCount }}</span>
        </div>
        <div class="health-item">
          <span class="health-item-label">路由快取 L1/L2</span>
          <span class="health-item-value">{{ cacheInfo?.routeMode }} {{ cacheInfo?.routeHitRate }}</span>
        </div>
        <div class="health-item">
          <span class="health-item-label">Workcenter</span>
          <span class="health-item-value">{{ cacheInfo?.workcenterCount }}</span>
        </div>
      </div>

      <!-- 背景服務 -->
      <div class="health-section-group">
        <div class="health-section-title">背景服務</div>
        <div class="health-item">
          <span class="health-item-label">RQ Workers</span>
          <span class="health-item-value">{{ bgServices?.rqWorkers }}</span>
        </div>
        <div class="health-item">
          <span class="health-item-label">MySQL Sync</span>
          <span class="health-item-value">{{ bgServices?.syncWorker }}</span>
        </div>
        <div class="health-item">
          <span class="health-item-label">Anomaly Scheduler</span>
          <span class="health-item-value">{{ bgServices?.anomaly }}</span>
        </div>
      </div>

      <div v-if="warnings.length" class="health-section health-section-warn">
        <h5>Warnings</h5>
        <ul>
          <li v-for="message in warnings" :key="message">{{ message }}</li>
        </ul>
      </div>

      <div v-if="frontendErrors.length" class="health-section health-section-error">
        <h5>Frontend Shell Errors</h5>
        <ul>
          <li v-for="message in frontendErrors" :key="message">{{ message }}</li>
        </ul>
      </div>
    </div>
  </div>
</template>
