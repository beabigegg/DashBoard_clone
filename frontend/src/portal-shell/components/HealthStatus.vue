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

const detail = ref({
  database: '--',
  redis: '--',
  cacheEnabled: '--',
  cacheUpdatedAt: '--',
  resourceCacheEnabled: '--',
  resourceCacheCount: '--',
  routeCacheMode: '--',
  routeCacheHitRate: '--',
  routeCacheDegraded: '--',
  frontendShell: '--',
});

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
      second: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

function normalizeHitRate(value) {
  if (value == null || value === '') return '--';
  return String(value);
}

function togglePopup() {
  popupOpen.value = !popupOpen.value;
}

function closePopup() {
  popupOpen.value = false;
}

function onDocumentClick(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest('#shellHealthWrap')) {
    return;
  }
  closePopup();
}

function onDocumentKeydown(event) {
  if (event.key === 'Escape') {
    closePopup();
  }
}

async function checkHealth() {
  try {
    const [healthResp, shellResp] = await Promise.all([
      fetch('/health', { cache: 'no-store' }),
      fetch('/health/frontend-shell', { cache: 'no-store' }),
    ]);

    if (!healthResp.ok) {
      throw new Error(`Health API ${healthResp.status}`);
    }

    const healthData = await healthResp.json();
    const shellData = shellResp.ok ? await shellResp.json() : null;

    status.value = healthData.status || 'unhealthy';
    label.value = labelFromHealthStatus(status.value);

    const frontendShell = normalizeFrontendShellHealth(shellData);
    detail.value = {
      database: toStatusText(healthData.services?.database || 'error'),
      redis: toStatusText(healthData.services?.redis || 'disabled'),
      cacheEnabled: healthData.cache?.enabled ? '已啟用' : '未啟用',
      cacheUpdatedAt: formatDateTime(healthData.cache?.updated_at),
      resourceCacheEnabled: healthData.resource_cache?.enabled
        ? (healthData.resource_cache?.loaded ? '已載入' : '未載入')
        : '未啟用',
      resourceCacheCount: healthData.resource_cache?.count != null
        ? `${healthData.resource_cache.count} 筆`
        : '--',
      routeCacheMode: healthData.route_cache?.mode || '--',
      routeCacheHitRate: `${normalizeHitRate(healthData.route_cache?.l1_hit_rate)} / ${normalizeHitRate(healthData.route_cache?.l2_hit_rate)}`,
      routeCacheDegraded: healthData.route_cache?.degraded ? '是' : '否',
      frontendShell: frontendShell.status === 'healthy' ? '正常' : '異常',
    };

    warnings.value = Array.isArray(healthData.warnings) ? healthData.warnings : [];
    frontendErrors.value = frontendShell.errors;
  } catch {
    const fallback = buildHealthFallbackDetail();
    status.value = fallback.status;
    label.value = fallback.label;
    detail.value = fallback.detail;
    warnings.value = [];
    frontendErrors.value = [];
  }
}

onMounted(() => {
  void checkHealth();
  timer = window.setInterval(() => {
    void checkHealth();
  }, 30000);
  document.addEventListener('click', onDocumentClick);
  document.addEventListener('keydown', onDocumentKeydown);
});

onUnmounted(() => {
  if (timer) {
    window.clearInterval(timer);
  }
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
      <div class="health-item">
        <span class="health-item-label">資料庫 (Oracle)</span>
        <span class="health-item-value">{{ detail.database }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">快取 (Redis)</span>
        <span class="health-item-value">{{ detail.redis }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">WIP 快取</span>
        <span class="health-item-value">{{ detail.cacheEnabled }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">WIP 最後同步</span>
        <span class="health-item-value">{{ detail.cacheUpdatedAt }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">設備主檔快取</span>
        <span class="health-item-value">{{ detail.resourceCacheEnabled }} / {{ detail.resourceCacheCount }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">路由快取模式</span>
        <span class="health-item-value">{{ detail.routeCacheMode }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">路由快取命中 (L1/L2)</span>
        <span class="health-item-value">{{ detail.routeCacheHitRate }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">路由快取降級</span>
        <span class="health-item-value">{{ detail.routeCacheDegraded }}</span>
      </div>
      <div class="health-item">
        <span class="health-item-label">Frontend Shell 資產</span>
        <span class="health-item-value">{{ detail.frontendShell }}</span>
      </div>

      <div v-if="warnings.length" class="health-section">
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
