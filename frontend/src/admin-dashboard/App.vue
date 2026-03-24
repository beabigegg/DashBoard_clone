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
];

const activeTabKey = ref(tabs[0].key);
const tabRef = ref(null);
const refreshing = ref(false);
const autoRefreshEnabled = ref(true);

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
  intervalMs: 30_000,
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
  <div class="theme-admin-dashboard dashboard-root">
    <header class="dashboard-header">
      <div class="dashboard-header-inner">
        <h1 class="dashboard-title">Admin Dashboard</h1>
        <div class="dashboard-header-actions">
          <label class="auto-refresh-toggle">
            <input
              type="checkbox"
              :checked="autoRefreshEnabled"
              @change="autoRefreshEnabled = !autoRefreshEnabled; toggleAutoRefresh()"
            />
            自動更新 (30s)
          </label>
          <button class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="refreshing" @click="refreshNow">
            {{ refreshing ? '更新中...' : '重新整理' }}
          </button>
        </div>
      </div>

      <nav class="dashboard-tabs" aria-label="Admin dashboard tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="dashboard-tab"
          :class="{ 'is-active': tab.key === activeTabKey }"
          @click="setActiveTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </nav>
    </header>

    <main class="dashboard-main">
      <KeepAlive>
        <component :is="currentTabComponent" ref="tabRef" />
      </KeepAlive>
    </main>
  </div>
</template>
