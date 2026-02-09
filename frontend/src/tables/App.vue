<script setup>
import { computed, onMounted } from 'vue';

import TableCatalog from './components/TableCatalog.vue';
import DataViewer from './components/DataViewer.vue';
import { useTableData } from './composables/useTableData.js';

const {
  tableConfig,
  selectedTable,
  columns,
  filters,
  rows,
  rowCount,
  hasQueried,
  loadingConfig,
  loadingColumns,
  loadingQuery,
  pageError,
  viewerError,
  activeFilterCount,
  loadTableConfig,
  selectTable,
  setFilter,
  removeFilter,
  clearFilters,
  queryTable,
  closeViewer,
} = useTableData();

const categories = computed(() => {
  return Object.entries(tableConfig.value || {}).map(([name, tables]) => ({
    name,
    tables: Array.isArray(tables) ? tables : [],
  }));
});

const isInitialLoading = computed(() => {
  return loadingConfig.value && categories.value.length === 0;
});

const isCatalogEmpty = computed(() => {
  return !loadingConfig.value && !pageError.value && categories.value.length === 0;
});

function handleSelectTable(table) {
  void selectTable(table);
}

function handleQuery() {
  void queryTable();
}

function handleRefreshCatalog() {
  void loadTableConfig();
}

onMounted(() => {
  void loadTableConfig();
});
</script>

<template>
  <div class="tables-page">
    <div class="container">
      <header class="header">
        <div>
          <h1>MES 數據表查詢工具</h1>
          <p>點擊表名載入欄位，輸入篩選條件後查詢，最多返回最後 1000 筆資料</p>
        </div>
        <button
          type="button"
          class="refresh-catalog-btn"
          :disabled="loadingConfig"
          @click="handleRefreshCatalog"
        >
          {{ loadingConfig ? '載入中...' : '重新載入清單' }}
        </button>
      </header>

      <main class="content">
        <div v-if="pageError" class="error-banner">
          {{ pageError }}
        </div>

        <div v-if="isInitialLoading" class="loading-panel">
          正在載入表格設定...
        </div>

        <div v-else-if="isCatalogEmpty" class="empty-state">
          尚無可用表格設定
        </div>

        <TableCatalog
          v-else
          :categories="categories"
          :selected-table-name="selectedTable?.name || ''"
          :disabled="loadingColumns || loadingQuery"
          @select-table="handleSelectTable"
        />

        <DataViewer
          v-if="selectedTable"
          :selected-table="selectedTable"
          :columns="columns"
          :filters="filters"
          :rows="rows"
          :row-count="rowCount"
          :active-filter-count="activeFilterCount"
          :has-queried="hasQueried"
          :loading-columns="loadingColumns"
          :loading-query="loadingQuery"
          :error-message="viewerError"
          @close="closeViewer"
          @query="handleQuery"
          @set-filter="setFilter"
          @remove-filter="removeFilter"
          @clear-filters="clearFilters"
        />
      </main>
    </div>
  </div>
</template>
