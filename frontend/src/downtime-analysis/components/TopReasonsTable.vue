<script setup lang="ts">
import type { TopReasonRow } from '../types';

defineProps<{
  rows: TopReasonRow[];
}>();
</script>

<template>
  <div class="top-reasons-section">
    <h3 class="section-title">停機原因 Top {{ rows.length }}</h3>
    <div v-if="rows.length === 0" class="empty-state" role="status">
      暫無資料
    </div>
    <div v-else class="table-wrapper" role="region" aria-label="停機原因列表">
      <table class="data-table" aria-label="停機原因列表">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">停機原因</th>
            <th scope="col">狀態</th>
            <th scope="col">時數 (h)</th>
            <th scope="col">事件數</th>
            <th scope="col">平均 (min)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="row.reason + row.status">
            <td>{{ idx + 1 }}</td>
            <td>{{ row.reason || '(未填寫)' }}</td>
            <td>
              <span class="status-badge" :class="`status-${row.status.toLowerCase()}`">
                {{ row.status }}
              </span>
            </td>
            <td>{{ row.hours.toFixed(2) }}</td>
            <td>{{ row.event_count }}</td>
            <td>{{ row.avg_min.toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
