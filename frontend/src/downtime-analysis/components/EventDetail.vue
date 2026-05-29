<script setup lang="ts">
import type { EventDetailRow, Pagination } from '../types';
import { formatDowntimeDate } from '../formatDowntimeDate';

const props = defineProps<{
  rows: EventDetailRow[];
  pagination: Pagination;
}>();

const emit = defineEmits<{
  (e: 'page-change', page: number): void;
}>();

/**
 * Render a JOB-derived field as '—' when the row's job object is null.
 * Contract: data-shape-contract.md §3.12.6 — Frontend MUST render all job-derived
 * fields as '—' when job is null (match_source='none').
 */
function jobField(row: EventDetailRow, key: keyof NonNullable<EventDetailRow['job']>): string {
  if (row.job === null) return '—';
  const value = row.job[key];
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return value.toFixed(1);
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
}

function matchSourceLabel(src: string): string {
  switch (src) {
    case 'jobid': return 'JOBID';
    case 'overlap': return '時間重疊';
    case 'none': return '未匹配';
    default: return src;
  }
}

function matchSourceClass(src: string): string {
  switch (src) {
    case 'jobid': return 'badge-success';
    case 'overlap': return 'badge-warning';
    case 'none': return 'badge-muted';
    default: return 'badge-muted';
  }
}

function goToPage(page: number): void {
  if (page < 1 || page > props.pagination.total_pages) return;
  emit('page-change', page);
}
</script>

<template>
  <div class="event-detail-section">
    <h3 class="section-title">停機事件明細</h3>

    <div v-if="rows.length === 0" class="empty-state" role="status">
      暫無資料
    </div>

    <div v-else>
      <div class="table-wrapper" role="region" aria-label="停機事件明細表">
        <table class="data-table event-detail-table" aria-label="停機事件明細">
          <thead>
            <tr>
              <th scope="col">設備ID</th>
              <th scope="col">設備名稱</th>
              <th scope="col">狀態</th>
              <th scope="col">原因</th>
              <th scope="col">類別</th>
              <th scope="col">開始時間</th>
              <th scope="col">結束時間</th>
              <th scope="col">時數 (h)</th>
              <th scope="col">橋接來源</th>
              <th scope="col">工單名稱</th>
              <th scope="col">機型</th>
              <th scope="col">症狀</th>
              <th scope="col">原因碼</th>
              <th scope="col">修復</th>
              <th scope="col">待料 (min)</th>
              <th scope="col">維修 (min)</th>
              <th scope="col">負責人</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.event_id"
              :class="{ 'row-no-job': row.job === null }"
            >
              <td>{{ row.resource_id }}</td>
              <td>{{ row.resource_name ?? '—' }}</td>
              <td>
                <span class="status-badge" :class="`status-${row.status.toLowerCase()}`">
                  {{ row.status }}
                </span>
              </td>
              <td>{{ row.reason ?? '—' }}</td>
              <td>{{ row.category }}</td>
              <td>{{ formatDowntimeDate(row.start_ts) }}</td>
              <td>{{ formatDowntimeDate(row.end_ts) }}</td>
              <td>{{ row.hours.toFixed(2) }}</td>
              <td>
                <span
                  class="match-badge"
                  :class="matchSourceClass(row.match_source)"
                  :aria-label="`橋接來源: ${matchSourceLabel(row.match_source)}`"
                >
                  {{ matchSourceLabel(row.match_source) }}
                  <span
                    v-if="row.job !== null && row.job.match_ambiguous"
                    class="ambiguous-indicator"
                    title="候補重疊率 ≥80%，匹配結果可能存疑"
                    aria-label="匹配存疑"
                  >⚠</span>
                </span>
              </td>
              <!-- JOB-derived fields: render '—' when job is null (match_source='none') -->
              <td>{{ jobField(row, 'job_order_name') }}</td>
              <td>{{ jobField(row, 'job_model') }}</td>
              <td>{{ jobField(row, 'symptom') }}</td>
              <td>{{ jobField(row, 'cause') }}</td>
              <td>{{ jobField(row, 'repair') }}</td>
              <td>{{ jobField(row, 'wait_min') }}</td>
              <td>{{ jobField(row, 'repair_min') }}</td>
              <td>{{ jobField(row, 'handler') }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination-row" role="navigation" aria-label="分頁導覽">
        <button
          type="button"
          class="page-btn"
          :disabled="pagination.page <= 1"
          aria-label="上一頁"
          @click="goToPage(pagination.page - 1)"
        >
          ‹
        </button>
        <span class="page-info">
          第 {{ pagination.page }} / {{ pagination.total_pages }} 頁
          （共 {{ pagination.total_rows }} 筆）
        </span>
        <button
          type="button"
          class="page-btn"
          :disabled="pagination.page >= pagination.total_pages"
          aria-label="下一頁"
          @click="goToPage(pagination.page + 1)"
        >
          ›
        </button>
      </div>
    </div>
  </div>
</template>
