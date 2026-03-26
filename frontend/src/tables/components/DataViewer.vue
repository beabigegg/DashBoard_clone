<script setup>
import { computed } from 'vue';

import Chip from '../../shared-ui/components/Chip.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';

const props = defineProps({
  selectedTable: {
    type: Object,
    required: true,
  },
  columns: {
    type: Array,
    default: () => [],
  },
  filters: {
    type: Object,
    default: () => ({}),
  },
  rows: {
    type: Array,
    default: () => [],
  },
  rowCount: {
    type: Number,
    default: 0,
  },
  activeFilterCount: {
    type: Number,
    default: 0,
  },
  hasQueried: {
    type: Boolean,
    default: false,
  },
  loadingColumns: {
    type: Boolean,
    default: false,
  },
  loadingQuery: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['close', 'query', 'set-filter', 'remove-filter', 'clear-filters']);

const activeFilters = computed(() => {
  const entries = Object.entries(props.filters || {});
  return entries
    .filter(([, value]) => String(value ?? '').trim().length > 0)
    .sort(([left], [right]) => {
      return props.columns.indexOf(left) - props.columns.indexOf(right);
    });
});

const viewerTitle = computed(() => {
  const displayName = props.selectedTable?.display_name || props.selectedTable?.name || '--';
  if (props.loadingColumns) {
    return `正在載入: ${displayName}`;
  }
  if (props.loadingQuery) {
    return `正在查詢: ${displayName}`;
  }
  if (props.hasQueried) {
    const suffix = props.activeFilterCount > 0 ? ` [${props.activeFilterCount} 個篩選]` : '';
    return `${displayName} (${props.rowCount} 筆)${suffix}`;
  }
  return `${displayName} (${props.columns.length} 欄位)`;
});

function onFilterInput(column, event) {
  emit('set-filter', column, event.target.value);
}

function onFilterEnter() {
  emit('query');
}

function isNil(value) {
  return value === null || value === undefined;
}
</script>

<template>
  <section class="data-viewer active">
    <div class="viewer-header">
      <h3>{{ viewerTitle }}</h3>
      <button type="button" class="close-btn" @click="$emit('close')">關閉</button>
    </div>

    <div class="stats">
      <div class="stat-item">
        <div class="stat-label">表名</div>
        <div class="stat-value stat-value-table-name">{{ selectedTable.name }}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">欄位數</div>
        <div class="stat-value">{{ columns.length }}</div>
      </div>
      <span class="filter-hint">在下方輸入框填入篩選條件 (模糊匹配)</span>
      <button
        type="button"
        class="query-btn"
        :disabled="loadingColumns || loadingQuery || columns.length === 0"
        @click="$emit('query')"
      >
        查詢
      </button>
      <button
        type="button"
        class="clear-btn"
        :disabled="loadingColumns || loadingQuery || columns.length === 0"
        @click="$emit('clear-filters')"
      >
        清除篩選
      </button>
    </div>

    <div v-if="activeFilters.length > 0" class="active-filters">
      <Chip
        v-for="[column, value] in activeFilters"
        :key="column"
        :label="`${column}: ${value}`"
        tone="brand"
        removable
        @remove="$emit('remove-filter', column)"
      />
    </div>

    <div class="table-container">
      <div v-if="loadingColumns" class="loading">正在載入欄位資訊...</div>
      <ErrorBanner v-else-if="errorMessage" :message="errorMessage" :dismissible="false" />
      <div v-else-if="columns.length === 0" class="empty-hint">尚未載入欄位資訊</div>
      <table v-else>
        <thead>
          <tr>
            <th v-for="column in columns" :key="`head-${column}`">{{ column }}</th>
          </tr>
          <tr class="filter-row">
            <th v-for="column in columns" :key="`filter-${column}`">
              <input
                type="text"
                placeholder="篩選..."
                :value="filters[column] || ''"
                @input="onFilterInput(column, $event)"
                @keydown.enter.prevent="onFilterEnter"
              />
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loadingQuery">
            <td :colspan="columns.length" class="loading">正在查詢資料...</td>
          </tr>
          <tr v-else-if="!hasQueried">
            <td :colspan="columns.length" class="empty-hint">
              請輸入篩選條件後點擊「查詢」，或直接點擊「查詢」載入最後 1000 筆資料
            </td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td :colspan="columns.length" class="empty-hint">查無資料</td>
          </tr>
          <tr v-for="(row, rowIndex) in rows" v-else :key="`row-${rowIndex}`">
            <td v-for="column in columns" :key="`cell-${rowIndex}-${column}`">
              <i v-if="isNil(row[column])" class="null-value">NULL</i>
              <span v-else>{{ row[column] }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
