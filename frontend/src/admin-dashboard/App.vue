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

import PageHeader from '../shared-ui/components/PageHeader.vue';
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
  <div class="theme-admin-dashboard dashboard-root" data-testid="admin-dashboard-app">
    <PageHeader
      title="Admin Dashboard"
      :refreshing="refreshing"
      @refresh="refreshNow"
    >
      <template #subtitle>
        <label class="auto-refresh-toggle">
          <input
            type="checkbox"
            :checked="autoRefreshEnabled"
            data-testid="auto-refresh-toggle"
            @change="autoRefreshEnabled = !autoRefreshEnabled; toggleAutoRefresh()"
          />
          自動更新 (30s)
        </label>
      </template>
    </PageHeader>

    <nav class="dashboard-tabs" aria-label="Admin dashboard tabs">
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
