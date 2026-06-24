<script setup lang="ts">
import type { TopReasonRow } from '../types';

const props = defineProps<{
  rows: TopReasonRow[];
  categoryColorMap?: Record<string, string>;
}>();

function categoryTagStyle(category: string): Record<string, string> {
  const color = props.categoryColorMap?.[category];
  if (!color) return {};
  return {
    '--cat-color': color,
    background: `${color}1e`,
    'border-color': `${color}70`,
    color,
  };
}

function catDotStyle(category: string): Record<string, string> {
  const color = props.categoryColorMap?.[category];
  if (!color) return {};
  return { 'background-color': color, '--cat-color': color };
}
</script>

<template>
  <div class="top-reasons-section">
    <h3 class="section-title">停機原因 Top {{ rows.length }}</h3>
    <div v-if="rows.length === 0" class="empty-state" role="status">
      暫無資料
    </div>
    <div v-else class="table-wrapper" role="region" aria-label="停機原因列表">
      <table class="data-table top-reasons-table" aria-label="停機原因列表">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">停機原因</th>
            <th scope="col">停機類別</th>
            <th scope="col">狀態</th>
            <th scope="col">時數 (h)</th>
            <th scope="col">事件數</th>
            <th scope="col">平均 (min)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="row.reason + row.status">
            <td>{{ idx + 1 }}</td>
            <td class="reason-cell">{{ row.reason || '(未填寫)' }}</td>
            <td>
              <span
                v-if="row.big_category"
                class="category-tag"
                :style="categoryTagStyle(row.big_category)"
              >
                <span class="cat-dot" :style="catDotStyle(row.big_category)" />
                {{ row.big_category }}
              </span>
              <span v-else class="category-tag category-tag--empty">—</span>
            </td>
            <td>
              <span class="status-badge" :class="`status-${row.status.toLowerCase()}`">
                {{ row.status }}
              </span>
            </td>
            <td class="num-cell">{{ row.hours.toFixed(2) }}</td>
            <td class="num-cell">{{ row.event_count }}</td>
            <td class="num-cell">{{ row.avg_min.toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
