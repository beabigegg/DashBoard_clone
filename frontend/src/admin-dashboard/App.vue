<script setup>
import {
  computed,
  defineAsyncComponent,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue';

import { useAutoRefresh } from '../shared-composables/useAutoRefresh.js';
import { apiGet } from '../core/api';

const tabs = [
  {
    key: 'overview',
    label: '總覽',
    component: defineAsyncComponent(() => import('./tabs/OverviewTab.vue')),
  },
  {
    key: 'performance',
    label: '效能',
    component: defineAsyncComponent(() => import('./tabs/PerformanceTab.vue')),
  },
  {
    key: 'cache',
    label: '快取',
    component: defineAsyncComponent(() => import('./tabs/CacheTab.vue')),
  },
  {
    key: 'worker',
    label: 'Worker',
    component: defineAsyncComponent(() => import('./tabs/WorkerTab.vue')),
  },
  {
    key: 'usage',
    label: '用戶',
    component: defineAsyncComponent(() => import('./tabs/UsageTab.vue')),
  },
  {
    key: 'logs',
    label: '日誌',
    component: defineAsyncComponent(() => import('./tabs/LogsTab.vue')),
  },
  {
    key: 'permissions',
    label: '目標值權限',
    component: defineAsyncComponent(() => import('./tabs/PermissionsTab.vue')),
  },
];

const activeTabKey = ref(tabs[0].key);
const tabRef = ref(null);
const refreshing = ref(false);
const autoRefreshEnabled = ref(true);

// Auto-refresh poll interval (ms). Defaults to 30s and is aligned to the backend
// metrics-snapshot cadence (METRICS_HISTORY_INTERVAL) once system-status is read,
// so polling stays in sync with how often the backend actually snapshots.
const DEFAULT_POLL_INTERVAL_MS = 30_000;
const pollIntervalMs = ref(DEFAULT_POLL_INTERVAL_MS);

async function syncPollInterval() {
  try {
    const resp = await apiGet('/admin/api/system-status');
    const seconds = resp?.data?.monitoring?.metrics_history_interval_seconds;
    if (typeof seconds === 'number' && seconds > 0) {
      pollIntervalMs.value = seconds * 1000;
    }
  } catch {
    // Non-fatal — keep the default poll interval.
  }
}

const currentTab = computed(
  () => tabs.find((tab) => tab.key === activeTabKey.value) || tabs[0],
);

const currentTabComponent = computed(() => currentTab.value.component);

async function refreshActiveTab() {
  await tabRef.value?.refresh?.();
}

async function refreshNow() {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    await refreshActiveTab();
  } finally {
    refreshing.value = false;
  }
}

const { startAutoRefresh, stopAutoRefresh } = useAutoRefresh({
  onRefresh: refreshNow,
  intervalMs: () => pollIntervalMs.value,
  autoStart: false,
});

function setActiveTab(tabKey) {
  if (tabKey !== activeTabKey.value) {
    activeTabKey.value = tabKey;
  }
}

function toggleAutoRefresh() {
  if (autoRefreshEnabled.value) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
}

watch(activeTabKey, async () => {
  await nextTick();
  await refreshNow();
});

onMounted(async () => {
  await nextTick();
  await syncPollInterval();
  await refreshNow();
  if (autoRefreshEnabled.value) {
    startAutoRefresh();
  }
});

onBeforeUnmount(() => {
  stopAutoRefresh();
});
</script>

<template>
  <div class="theme-admin-dashboard dashboard-root" data-testid="admin-dashboard-app">
    <nav class="dashboard-tabs" aria-label="Admin dashboard tabs">
      <div class="dashboard-tabs__list">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="dashboard-tab"
          :class="{ 'is-active': tab.key === activeTabKey }"
          :data-testid="`tab-${tab.key}`"
          @click="setActiveTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="dashboard-toolbar">
        <label class="auto-refresh-toggle">
          <input
            type="checkbox"
            :checked="autoRefreshEnabled"
            data-testid="auto-refresh-toggle"
            @change="autoRefreshEnabled = !autoRefreshEnabled; toggleAutoRefresh()"
          />
          自動更新 (30s)
        </label>
        <button
          type="button"
          class="dashboard-refresh-btn"
          :disabled="refreshing"
          data-testid="dashboard-refresh"
          @click="refreshNow"
        >
          <span v-if="refreshing" class="dashboard-refresh-btn__spinner" aria-hidden="true"></span>
          {{ refreshing ? '更新中…' : '重新整理' }}
        </button>
      </div>
    </nav>

    <main class="dashboard-main">
      <KeepAlive>
        <component
          :is="currentTabComponent"
          ref="tabRef"
          :data-testid="`panel-${activeTabKey}`"
        />
      </KeepAlive>
    </main>
  </div>
</template>
