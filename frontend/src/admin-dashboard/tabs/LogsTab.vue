<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { apiPost } from '../../core/api.js';
import { useLogs } from '../../admin-shared/composables/useAdminData.js';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import LoadingSpinner from '../../shared-ui/components/LoadingSpinner.vue';
import SectionCard from '../../shared-ui/components/SectionCard.vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';

const logLevel = ref('');
const logSearch = ref('');
const logOffset = ref(0);
const logLimit = ref(50);
const cleanupLoading = ref(false);

const logsHook = useLogs(logLevel, logSearch, logLimit, logOffset);
const logsData = computed(() => logsHook.data.value || null);
const logsLoading = computed(() => logsHook.loading.value);
const errorMessage = computed(() => logsHook.error.value || '');

let debounceTimer = null;

async function loadLogs() {
  await logsHook.refresh();
}

function onLevelChange() {
  logOffset.value = 0;
  void loadLogs();
}

function onSearchInput() {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(() => {
    logOffset.value = 0;
    void loadLogs();
  }, 300);
}

async function cleanupLogs() {
  cleanupLoading.value = true;
  try {
    await apiPost('/admin/api/logs/cleanup', {});
    await loadLogs();
  } finally {
    cleanupLoading.value = false;
  }
}

function previousPage() {
  if (logOffset.value === 0) return;
  logOffset.value -= logLimit.value;
  void loadLogs();
}

function nextPage() {
  if (logOffset.value + logLimit.value >= (logsData.value?.total || 0)) return;
  logOffset.value += logLimit.value;
  void loadLogs();
}

const currentPage = computed(() => Math.floor(logOffset.value / logLimit.value) + 1);
const totalPages = computed(() => {
  const total = logsData.value?.total || 0;
  return Math.max(1, Math.ceil(total / logLimit.value));
});

async function refresh() {
  await loadLogs();
}

defineExpose({ refresh });

onMounted(() => {
  void loadLogs();
});

onBeforeUnmount(() => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
});
</script>

<template>
  <div class="logs-tab">
    <ErrorBanner :message="errorMessage" :dismissible="false" />

    <SectionCard>
      <template #header><h2 class="panel-title">系統日誌</h2></template>
      <div class="log-controls">
        <select v-model="logLevel" @change="onLevelChange">
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
          @input="onSearchInput"
        />
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :class="{ 'is-loading': cleanupLoading }"
          :disabled="cleanupLoading"
          @click="cleanupLogs"
        >
          <LoadingSpinner v-if="cleanupLoading" size="sm" />
          {{ cleanupLoading ? '清理中...' : '清理日誌' }}
        </button>
      </div>

      <div class="log-table-wrapper">
        <DataTable
          :data="logsData?.logs || []"
          :loading="logsLoading"
          :pagination="(logsData?.total || 0) > logLimit ? { page: currentPage, totalPages: totalPages, infoText: `共 ${logsData?.total || 0} 筆` } : null"
          @page-change="(p) => { logOffset = (p - 1) * logLimit; loadLogs(); }"
        >
          <DataTableColumn columnKey="timestamp" label="時間" />
          <DataTableColumn columnKey="level" label="等級" />
          <DataTableColumn columnKey="message" label="訊息" />
          <template #cell="{ row, columnKey, value }">
            <template v-if="columnKey === 'timestamp'">
              <span class="log-time">{{ value }}</span>
            </template>
            <template v-else-if="columnKey === 'level'">
              <span class="log-level" :class="'log-level--' + (value || '').toLowerCase()">{{ value }}</span>
            </template>
            <template v-else-if="columnKey === 'message'">
              <span class="log-msg">{{ value }}</span>
            </template>
            <template v-else>{{ value }}</template>
          </template>
        </DataTable>
      </div>
    </SectionCard>
  </div>
</template>
