<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { apiPost } from '../../core/api.js';
import { formatLogTime } from '../../core/datetime.js';
import { useLogs, useStorageInfo } from '../../admin-shared/composables/useAdminData';
import { useLastUpdated } from '../../admin-shared/composables/useLastUpdated';
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
const storagePurging = ref(false);

const logsHook = useLogs(logLevel, logSearch, logLimit, logOffset);
const storageHook = useStorageInfo();
const { lastUpdatedLabel, markUpdated } = useLastUpdated();

const logsData = computed(() => logsHook.data.value || null);
const logsLoading = computed(() => logsHook.loading.value);
const storageInfo = computed(() => storageHook.data.value || null);
const errorMessage = computed(() => logsHook.error.value || storageHook.error.value || '');

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
  if (!window.confirm('確定要清理所有日誌？')) return;
  cleanupLoading.value = true;
  try {
    const result = await apiPost('/admin/api/logs/cleanup', { clear_all: true });
    const deleted = result?.data?.deleted ?? 0;
    if (deleted > 0) {
      window.alert(`已清理 ${deleted} 筆日誌`);
    }
    await loadLogs();
  } catch (err) {
    window.alert('清理日誌失敗：' + (err.message || '未知錯誤'));
  } finally {
    cleanupLoading.value = false;
  }
}

async function purgeMetricsHistory() {
  if (!window.confirm('確定要清除所有效能快照資料？清除後趨勢圖將重新累積。')) {
    return;
  }
  storagePurging.value = true;
  try {
    await apiPost('/admin/api/performance-history/purge', {});
    await storageHook.refresh();
  } catch (err) {
    window.alert('清除快照失敗：' + (err.message || '未知錯誤'));
  } finally {
    storagePurging.value = false;
  }
}

async function cleanupLogFiles(targets) {
  const label = targets.includes('archive') ? 'Archive 目錄' : 'Log 檔案';
  if (!window.confirm(`確定要清理${label}？`)) return;
  storagePurging.value = true;
  try {
    await apiPost('/admin/api/log-files/cleanup', { targets });
    await storageHook.refresh();
  } catch (err) {
    window.alert('清理失敗：' + (err.message || '未知錯誤'));
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
  await Promise.all([logsHook.refresh(), storageHook.refresh()]);
  markUpdated();
}

defineExpose({ refresh });

onMounted(() => {
  void refresh();
});

onBeforeUnmount(() => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
});
</script>

<template>
  <div class="logs-tab">
    <div class="admin-tab__last-updated" role="status" aria-live="polite">{{ lastUpdatedLabel }}</div>
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
              <span class="log-time">{{ formatLogTime(value) }}</span>
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

    <SectionCard v-if="storageInfo?.sqlite_files?.length">
      <template #header><h2 class="panel-title">SQLite 資料庫</h2></template>
      <DataTable :data="storageInfo.sqlite_files">
        <DataTableColumn columnKey="path" label="檔案" />
        <DataTableColumn columnKey="size_bytes" label="大小" align="right" />
        <DataTableColumn columnKey="actions" label="操作" />
        <template #cell="{ row, columnKey }">
          <template v-if="columnKey === 'size_bytes'">{{ formatBytes(row.size_bytes) }}</template>
          <template v-else-if="columnKey === 'actions'">
            <button
              v-if="row.path.includes('metrics_history')"
              class="ui-btn ui-btn--danger ui-btn--sm"
              :disabled="storagePurging"
              @click="purgeMetricsHistory"
            >
              清除快照
            </button>
          </template>
          <template v-else>{{ row[columnKey] }}</template>
        </template>
      </DataTable>
    </SectionCard>

    <SectionCard v-if="storageInfo?.log_files?.length">
      <template #header><h2 class="panel-title">Log 檔案</h2></template>
      <DataTable :data="storageInfo.log_files">
        <DataTableColumn columnKey="path" label="檔案" />
        <DataTableColumn columnKey="size_bytes" label="大小" align="right" />
        <template #cell="{ row, columnKey }">
          <template v-if="columnKey === 'size_bytes'">{{ formatBytes(row.size_bytes) }}</template>
          <template v-else>{{ row[columnKey] }}</template>
        </template>
      </DataTable>
      <div class="storage-actions">
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :class="{ 'is-loading': storagePurging }"
          :disabled="storagePurging"
          @click="cleanupLogFiles(['logs'])"
        >
          <LoadingSpinner v-if="storagePurging" size="sm" />
          {{ storagePurging ? '清理中...' : '清空 Log 檔案' }}
        </button>
      </div>
    </SectionCard>

    <SectionCard v-if="storageInfo?.archive_files?.length">
      <template #header>
        <h2 class="panel-title">Archive 歷史檔</h2>
      </template>
      <DataTable :data="storageInfo.archive_files">
        <DataTableColumn columnKey="path" label="檔案" />
        <DataTableColumn columnKey="size_bytes" label="大小" align="right" />
        <template #cell="{ row, columnKey }">
          <template v-if="columnKey === 'size_bytes'">{{ formatBytes(row.size_bytes) }}</template>
          <template v-else>{{ row[columnKey] }}</template>
        </template>
      </DataTable>
      <div class="storage-actions">
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :class="{ 'is-loading': storagePurging }"
          :disabled="storagePurging"
          @click="cleanupLogFiles(['archive'])"
        >
          <LoadingSpinner v-if="storagePurging" size="sm" />
          {{ storagePurging ? '清理中...' : '清空 Archive' }}
        </button>
      </div>
    </SectionCard>
  </div>
</template>
