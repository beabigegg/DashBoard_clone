<script setup lang="ts">
import { ref, computed } from 'vue';
import type { EquipmentDetailRow } from '../types';

const props = defineProps<{
  rows: EquipmentDetailRow[];
}>();

type SortKey = keyof EquipmentDetailRow;
const sortKey = ref<SortKey>('total_hours');
const sortAsc = ref(false);

function toggleSort(key: SortKey): void {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value;
  } else {
    sortKey.value = key;
    sortAsc.value = false;
  }
}

function sortIndicator(key: SortKey): string {
  if (sortKey.value !== key) return '';
  return sortAsc.value ? '▲' : '▼';
}

const sortedRows = computed(() => {
  const copy = [...props.rows];
  copy.sort((a, b) => {
    const av = a[sortKey.value];
    const bv = b[sortKey.value];
    let cmp = 0;
    if (typeof av === 'number' && typeof bv === 'number') {
      cmp = av - bv;
    } else {
      cmp = String(av ?? '').localeCompare(String(bv ?? ''), 'zh-Hant');
    }
    return sortAsc.value ? cmp : -cmp;
  });
  return copy;
});
</script>

<template>
  <div class="equipment-detail-section">
    <h3 class="section-title">設備停機明細</h3>
    <div v-if="rows.length === 0" class="empty-state" role="status">
      暫無資料
    </div>
    <div v-else class="table-wrapper" role="region" aria-label="設備停機明細表">
      <table class="data-table" aria-label="設備停機明細">
        <thead>
          <tr>
            <th scope="col">
              <button type="button" class="sort-btn" @click="toggleSort('resource_id')">
                設備ID {{ sortIndicator('resource_id') }}
              </button>
            </th>
            <th scope="col">設備名稱</th>
            <th scope="col">工作站</th>
            <th scope="col">機種</th>
            <th scope="col">
              <button type="button" class="sort-btn" @click="toggleSort('udt_hours')">
                UDT (h) {{ sortIndicator('udt_hours') }}
              </button>
            </th>
            <th scope="col">
              <button type="button" class="sort-btn" @click="toggleSort('sdt_hours')">
                SDT (h) {{ sortIndicator('sdt_hours') }}
              </button>
            </th>
            <th scope="col">
              <button type="button" class="sort-btn" @click="toggleSort('egt_hours')">
                EGT (h) {{ sortIndicator('egt_hours') }}
              </button>
            </th>
            <th scope="col">
              <button type="button" class="sort-btn" @click="toggleSort('total_hours')">
                總計 (h) {{ sortIndicator('total_hours') }}
              </button>
            </th>
            <th scope="col">
              <button type="button" class="sort-btn" @click="toggleSort('event_count')">
                事件數 {{ sortIndicator('event_count') }}
              </button>
            </th>
            <th scope="col">主要原因</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in sortedRows" :key="row.resource_id">
            <td>{{ row.resource_id }}</td>
            <td>{{ row.resource_name ?? '—' }}</td>
            <td>{{ row.workcenter ?? '—' }}</td>
            <td>{{ row.family ?? '—' }}</td>
            <td>{{ row.udt_hours.toFixed(2) }}</td>
            <td>{{ row.sdt_hours.toFixed(2) }}</td>
            <td>{{ row.egt_hours.toFixed(2) }}</td>
            <td>{{ row.total_hours.toFixed(2) }}</td>
            <td>{{ row.event_count }}</td>
            <td>{{ row.top_reason ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
