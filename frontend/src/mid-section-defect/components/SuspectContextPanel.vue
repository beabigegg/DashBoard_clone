<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue';

import { apiGet } from '../../core/api.js';

const props = defineProps({
  machine: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['close']);

const jobsLoading = ref(false);
const jobs = ref([]);
const jobsError = ref('');

watch(() => props.machine, async (val) => {
  jobs.value = [];
  jobsError.value = '';
  if (!val?.EQUIPMENT_ID) return;
  jobsLoading.value = true;
  try {
    const result = await apiGet(`/api/query-tool/equipment-recent-jobs/${encodeURIComponent(val.EQUIPMENT_ID)}`);
    if (Array.isArray(result?.data)) {
      jobs.value = result.data;
    }
  } catch (err) {
    jobsError.value = err.message || '載入維修紀錄失敗';
  } finally {
    jobsLoading.value = false;
  }
}, { immediate: true });

function handleOutsideClick(e) {
  const el = e.target.closest('.suspect-panel');
  if (!el) emit('close');
}

onMounted(() => {
  setTimeout(() => document.addEventListener('click', handleOutsideClick), 0);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick);
});

function formatDate(v) {
  if (!v) return '-';
  return String(v).slice(0, 16).replace('T', ' ');
}

function formatNumber(v) {
  if (v == null) return '0';
  return Number(v).toLocaleString();
}
</script>

<template>
  <div v-if="machine" class="suspect-panel" @click.stop>
    <div class="panel-header">
      <h4 class="panel-title">{{ machine.EQUIPMENT_NAME }}</h4>
      <button type="button" class="panel-close" @click="emit('close')">&times;</button>
    </div>

    <div class="panel-section">
      <h5 class="section-label">歸因摘要</h5>
      <table class="attr-table">
        <tbody>
          <tr><td class="attr-key">站點</td><td>{{ machine.WORKCENTER_GROUP || '-' }}</td></tr>
          <tr><td class="attr-key">機型</td><td>{{ machine.RESOURCEFAMILYNAME || '-' }}</td></tr>
          <tr><td class="attr-key">歸因不良率</td><td>{{ machine.DEFECT_RATE != null ? Number(machine.DEFECT_RATE).toFixed(2) + '%' : '-' }}</td></tr>
          <tr><td class="attr-key">歸因不良數</td><td>{{ formatNumber(machine.DEFECT_QTY) }}</td></tr>
          <tr><td class="attr-key">歸因投入數</td><td>{{ formatNumber(machine.INPUT_QTY) }}</td></tr>
          <tr><td class="attr-key">關聯 LOT 數</td><td>{{ formatNumber(machine.DETECTION_LOT_COUNT) }}</td></tr>
        </tbody>
      </table>
    </div>

    <div class="panel-section">
      <h5 class="section-label">近期維修紀錄</h5>
      <div v-if="jobsLoading" class="jobs-loading">載入中...</div>
      <div v-else-if="jobsError" class="jobs-error">{{ jobsError }}</div>
      <div v-else-if="jobs.length === 0" class="jobs-empty">近 30 天無維修紀錄</div>
      <table v-else class="jobs-table">
        <thead>
          <tr>
            <th>JOB ID</th>
            <th>狀態</th>
            <th>型號</th>
            <th>維修區間</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.JOBID">
            <td>{{ job.JOBID || '-' }}</td>
            <td>{{ job.JOBSTATUS || '-' }}</td>
            <td>{{ job.JOBMODELNAME || '-' }}</td>
            <td class="job-interval">
              <span>{{ formatDate(job.CREATEDATE) }}</span>
              <span v-if="job.COMPLETEDATE" class="interval-sep">→</span>
              <span v-if="job.COMPLETEDATE">{{ formatDate(job.COMPLETEDATE) }}</span>
              <span v-else class="interval-ongoing">進行中</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.suspect-panel {
  position: absolute;
  top: 0;
  right: -320px;
  width: 300px;
  background: var(--bg-primary, theme('colors.token.hffffff'));
  border: 1px solid var(--border-color, theme('colors.token.he5e7eb'));
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  z-index: 100;
  font-size: 13px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: theme('spacing.token.p10') theme('spacing.token.p14');
  border-bottom: 1px solid var(--border-color, theme('colors.token.he5e7eb'));
}
.panel-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.panel-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--text-tertiary, theme('colors.token.h9ca3af'));
  padding: 0 theme('spacing.token.p4');
  line-height: 1;
}
.panel-section {
  padding: theme('spacing.token.p10') theme('spacing.token.p14');
}
.panel-section + .panel-section {
  border-top: 1px solid var(--border-color, theme('colors.token.hf3f4f6'));
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary, theme('colors.token.h6b7280'));
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin: 0 0 theme('spacing.token.p8');
}
.attr-table {
  width: 100%;
  border-collapse: collapse;
}
.attr-table td {
  padding: theme('spacing.token.p3') 0;
  line-height: 1.4;
}
.attr-key {
  color: var(--text-secondary, theme('colors.token.h6b7280'));
  width: 90px;
  white-space: nowrap;
}
.jobs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.jobs-table th {
  text-align: left;
  font-weight: 600;
  color: var(--text-secondary, theme('colors.token.h6b7280'));
  padding: theme('spacing.token.p4') theme('spacing.token.p6') theme('spacing.token.p4') 0;
  border-bottom: 1px solid var(--border-color, theme('colors.token.he5e7eb'));
  font-size: 11px;
}
.jobs-table td {
  padding: theme('spacing.token.p4') theme('spacing.token.p6') theme('spacing.token.p4') 0;
  border-bottom: 1px solid var(--border-color, theme('colors.token.hf3f4f6'));
}
.job-interval {
  font-size: 11px;
  line-height: 1.5;
}
.interval-sep {
  margin: 0 theme('spacing.token.p2');
  color: var(--text-tertiary, theme('colors.token.h9ca3af'));
}
.interval-ongoing {
  color: theme('colors.state.warning');
  font-size: 10px;
  font-weight: 500;
}
.jobs-loading,
.jobs-empty {
  color: var(--text-tertiary, theme('colors.token.h9ca3af'));
  font-size: 12px;
  padding: theme('spacing.token.p4') 0;
}
.jobs-error {
  color: theme('colors.state.danger');
  font-size: 12px;
  padding: theme('spacing.token.p4') 0;
}
</style>
