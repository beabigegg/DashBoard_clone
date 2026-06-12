<script setup lang="ts">
/**
 * MachineEventRows — Tier 3 lazy-loaded events display for a single machine+status.
 *
 * On mount, emits 'mount' so the parent can trigger the loadMachineStatusEvents call.
 * Renders loading / error / empty-state / event rows based on the cacheEntry prop.
 *
 * Change: downtime-analysis-page-redesign (IP-6b)
 */
import { onMounted } from 'vue';
import type { TierThreeEntry } from '../types';
import { formatDowntimeDate } from '../formatDowntimeDate';

const props = defineProps<{
  cacheEntry: TierThreeEntry | undefined;
}>();

const emit = defineEmits<{
  'mount': [];
}>();

onMounted(() => {
  emit('mount');
});

function matchBadgeClass(source: string): string {
  if (source === 'jobid') return 'match-badge badge-success';
  if (source === 'overlap') return 'match-badge badge-warning';
  return 'match-badge badge-neutral';
}

function matchSourceLabel(source: string): string {
  if (source === 'jobid') return 'JOBID';
  if (source === 'overlap') return '重疊';
  return '無';
}

/** Format a nullable minute value: show integer with unit, or — */
function fmtMin(v: number | null | undefined): string {
  if (v == null) return '—';
  return String(Math.round(v));
}

/** Sum two nullable minute fields; returns null only when both are null. */
function sumMin(a: number | null | undefined, b: number | null | undefined): number | null {
  if (a == null && b == null) return null;
  return (a ?? 0) + (b ?? 0);
}
</script>

<template>
  <div class="machine-event-rows">
    <!-- Loading state -->
    <div
      v-if="!cacheEntry || cacheEntry.loading"
      class="event-rows-loading"
      role="status"
      aria-label="載入事件中"
    >
      <span class="loading-spinner-sm"></span> 載入事件中...
    </div>

    <!-- Error state -->
    <div v-else-if="cacheEntry.error" class="event-rows-error" role="alert">
      {{ cacheEntry.error }}
    </div>

    <!-- Empty state -->
    <div
      v-else-if="cacheEntry.rows.length === 0"
      class="event-rows-empty"
      role="status"
    >
      此設備在此狀態下無事件記錄
    </div>

    <!-- Event rows table -->
    <table v-else class="event-inner-table">
      <thead>
        <!-- Row 1: column group labels -->
        <tr class="col-group-row">
          <th colspan="6" class="col-group col-group-event">停機事件</th>
          <th colspan="9" class="col-group col-group-job">JOB 資訊</th>
          <th colspan="4" class="col-group col-group-time">工單時間（分）</th>
        </tr>
        <!-- Row 2: individual column names -->
        <tr>
          <th>狀態</th>
          <th>原因</th>
          <th>類別</th>
          <th>開始時間</th>
          <th>結束時間</th>
          <th>時數(h)</th>
          <th>橋接</th>
          <th>建立時間</th>
          <th>結案時間</th>
          <th>JOB ID</th>
          <th>機型</th>
          <th>症狀</th>
          <th>原因碼</th>
          <th>修復</th>
          <th>負責人</th>
          <th title="工單建立到工程師接單的總等待時間（待分派 + 待接單）">待派接</th>
          <th title="工程師實際維修作業時間">維修</th>
          <th title="驗機階段時間（無驗機則為 —）">驗機</th>
          <th title="維修完成到工單結案的等待時間">結單等待</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="event in cacheEntry.rows" :key="event.event_id">
          <!-- 停機事件 group -->
          <td>
            <span :class="['status-badge', `badge-${event.status.toLowerCase()}`]">
              {{ event.status }}
            </span>
          </td>
          <td>{{ event.reason ?? '—' }}</td>
          <td>{{ event.category }}</td>
          <td>{{ formatDowntimeDate(event.start_ts) }}</td>
          <td>{{ formatDowntimeDate(event.end_ts) }}</td>
          <td>{{ event.hours.toFixed(2) }}</td>
          <!-- JOB 資訊 group -->
          <td>
            <span :class="matchBadgeClass(event.match_source)">
              {{ matchSourceLabel(event.match_source) }}
            </span>
          </td>
          <td class="ts-cell">{{ event.job?.job_create_date ? formatDowntimeDate(event.job.job_create_date) : '—' }}</td>
          <td class="ts-cell">{{ event.job?.job_complete_date ? formatDowntimeDate(event.job.job_complete_date) : '—' }}</td>
          <td>{{ event.job?.job_id ?? '—' }}</td>
          <td>{{ event.job?.job_model ?? '—' }}</td>
          <td>{{ event.job?.symptom ?? '—' }}</td>
          <td>{{ event.job?.cause ?? '—' }}</td>
          <td>{{ event.job?.repair ?? '—' }}</td>
          <td>{{ event.job?.handler ?? '—' }}</td>
          <!-- 工單時間 group -->
          <td class="time-cell">{{ fmtMin(sumMin(event.job?.wait_assign_min, event.job?.wait_ack_min)) }}</td>
          <td class="time-cell">{{ fmtMin(event.job?.repair_min) }}</td>
          <td class="time-cell" :class="{ 'time-cell--highlight': (event.job?.inspect_min ?? 0) > 0 }">
            {{ fmtMin(event.job?.inspect_min) }}
          </td>
          <td class="time-cell" :class="{ 'time-cell--warn': (event.job?.close_wait_min ?? 0) > 120 }">
            {{ fmtMin(event.job?.close_wait_min) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
