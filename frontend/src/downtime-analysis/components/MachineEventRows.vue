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
        <tr>
          <th>狀態</th>
          <th>原因</th>
          <th>類別</th>
          <th>開始時間</th>
          <th>結束時間</th>
          <th>時數(h)</th>
          <th>橋接來源</th>
          <th>工單</th>
          <th>機型</th>
          <th>症狀</th>
          <th>原因碼</th>
          <th>修復</th>
          <th>待料(分)</th>
          <th>維修(分)</th>
          <th>負責人</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="event in cacheEntry.rows" :key="event.event_id">
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
          <td>
            <span :class="matchBadgeClass(event.match_source)">
              {{ matchSourceLabel(event.match_source) }}
            </span>
          </td>
          <td>{{ event.job?.job_order_name ?? '—' }}</td>
          <td>{{ event.job?.job_model ?? '—' }}</td>
          <td>{{ event.job?.symptom ?? '—' }}</td>
          <td>{{ event.job?.cause ?? '—' }}</td>
          <td>{{ event.job?.repair ?? '—' }}</td>
          <td>{{ event.job?.wait_min?.toFixed(0) ?? '—' }}</td>
          <td>{{ event.job?.repair_min?.toFixed(0) ?? '—' }}</td>
          <td>{{ event.job?.handler ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
