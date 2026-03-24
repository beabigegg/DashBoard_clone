<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { apiPost } from '../../core/api.js';
import { useLogs } from '../../admin-shared/composables/useAdminData.js';

const logLevel = ref('');
const logSearch = ref('');
const logOffset = ref(0);
const logLimit = ref(50);
const cleanupLoading = ref(false);

const logsHook = useLogs(logLevel, logSearch, logLimit, logOffset);
const logsData = computed(() => logsHook.data.value || null);
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
    <section v-if="errorMessage" class="panel panel-disabled">
      <p class="muted">{{ errorMessage }}</p>
    </section>

    <section class="panel">
      <h2 class="panel-title">系統日誌</h2>
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
        <button class="ui-btn ui-btn--ghost ui-btn--sm" @click="cleanupLogs" :disabled="cleanupLoading">
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
            <tr
              v-for="(log, index) in logsData.logs"
              :key="index"
              :class="'log-' + (log.level || '').toLowerCase()"
            >
              <td class="log-time">{{ log.timestamp }}</td>
              <td class="log-level">{{ log.level }}</td>
              <td class="log-msg">{{ log.message }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">無日誌</p>
      </div>

      <div class="log-pagination" v-if="(logsData?.total || 0) > logLimit">
        <button class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="logOffset === 0" @click="previousPage">上一頁</button>
        <span>{{ currentPage }} / {{ totalPages }}</span>
        <button
          class="ui-btn ui-btn--ghost ui-btn--sm"
          :disabled="logOffset + logLimit >= (logsData?.total || 0)"
          @click="nextPage"
        >
          下一頁
        </button>
      </div>
    </section>
  </div>
</template>
