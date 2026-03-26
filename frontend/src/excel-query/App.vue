<script setup>
import { onMounted, ref } from 'vue';

import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import FilterToolbar from '../shared-ui/components/FilterToolbar.vue';
import SectionCard from '../shared-ui/components/SectionCard.vue';
import { useExcelQueryData } from './composables/useExcelQueryData.js';

const fileInput = ref(null);

const {
  uploadState,
  loading,
  errorMessage,
  successMessage,
  excelColumns,
  excelPreview,
  excelColumnValues,
  detectedColumnType,
  tableOptions,
  tableMetadata,
  tableColumns,
  filters,
  queryResult,
  availableReturnColumns,
  isDateRangeEnabled,
  hydrateFiltersFromUrl,
  loadTables,
  uploadExcel,
  loadExcelColumnValues,
  loadTableMetadata,
  executeQuery,
  exportCsv,
} = useExcelQueryData();

function formatCell(value) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
}

async function onUploadClick() {
  const file = fileInput.value?.files?.[0];
  await uploadExcel(file || null);
}

onMounted(async () => {
  hydrateFiltersFromUrl();
  await loadTables();
  if (filters.tableName) {
    await loadTableMetadata();
  }
});
</script>

<template>
  <div class="excel-query-page u-content-shell theme-excel-query">
    <header class="excel-query-header">
      <h1>Excel 批次查詢</h1>
    </header>

    <div class="u-panel-stack">
      <SectionCard>
        <template #header>
          <strong>Step 1. 上傳 Excel</strong>
        </template>

        <FilterToolbar>
          <input ref="fileInput" type="file" accept=".xls,.xlsx" />
          <template #actions>
            <button type="button" class="excel-btn excel-btn-primary" :disabled="uploadState.uploading" @click="onUploadClick">
              {{ uploadState.uploading ? '上傳中...' : '上傳' }}
            </button>
          </template>
        </FilterToolbar>
        <p class="excel-meta">檔名：{{ uploadState.fileName || '-' }}</p>
        <DataTable v-if="excelPreview.length > 0" :data="excelPreview">
          <DataTableColumn v-for="column in excelColumns" :key="column" :column-key="column" :label="column" />
          <template #cell="{ value }">{{ formatCell(value) }}</template>
        </DataTable>
      </SectionCard>

      <SectionCard>
        <template #header>
          <strong>Step 2. Excel 欄位與查詢值</strong>
        </template>
        <FilterToolbar>
          <label class="excel-filter">
            <span>Excel 欄位</span>
            <select v-model="filters.excelColumn" @change="loadExcelColumnValues">
              <option value="">請選擇</option>
              <option v-for="column in excelColumns" :key="column" :value="column">{{ column }}</option>
            </select>
          </label>
          <template #actions>
            <button type="button" class="excel-btn excel-btn-ghost" :disabled="loading.values" @click="loadExcelColumnValues">
              {{ loading.values ? '讀取中...' : '重新讀取欄位值' }}
            </button>
          </template>
        </FilterToolbar>
        <p class="excel-meta">偵測型別：{{ detectedColumnType || '-' }}</p>
        <p class="excel-meta">查詢值數量：{{ excelColumnValues.length }}</p>
      </SectionCard>

      <SectionCard>
        <template #header>
          <strong>Step 3. 資料表與查詢條件</strong>
        </template>
        <FilterToolbar>
          <label class="excel-filter">
            <span>目標資料表</span>
            <select v-model="filters.tableName" @change="loadTableMetadata">
              <option value="">請選擇</option>
              <option v-for="table in tableOptions" :key="table.name" :value="table.name">
                {{ table.display_name }} ({{ table.name }})
              </option>
            </select>
          </label>

          <label class="excel-filter">
            <span>查詢欄位</span>
            <select v-model="filters.searchColumn">
              <option value="">請選擇</option>
              <option v-for="column in tableColumns" :key="column.name" :value="column.name">{{ column.name }}</option>
            </select>
          </label>

          <label class="excel-filter">
            <span>查詢類型</span>
            <select v-model="filters.queryType">
              <option value="in">IN</option>
              <option value="like_contains">包含</option>
              <option value="like_prefix">前綴</option>
              <option value="like_suffix">後綴</option>
            </select>
          </label>
        </FilterToolbar>

        <div class="excel-return-cols">
          <p class="excel-meta">回傳欄位（可複選）</p>
          <label
            v-for="column in availableReturnColumns"
            :key="column"
            class="excel-checkbox-item"
          >
            <input v-model="filters.returnColumns" type="checkbox" :value="column" />
            <span>{{ column }}</span>
          </label>
        </div>

        <FilterToolbar v-if="isDateRangeEnabled">
          <label class="excel-filter">
            <span>日期欄位</span>
            <input v-model="filters.dateColumn" type="text" :placeholder="tableMetadata?.time_field || ''" />
          </label>
          <label class="excel-filter">
            <span>開始</span>
            <input v-model="filters.dateFrom" type="date" />
          </label>
          <label class="excel-filter">
            <span>結束</span>
            <input v-model="filters.dateTo" type="date" />
          </label>
        </FilterToolbar>

        <div class="excel-action-row">
          <button type="button" class="excel-btn excel-btn-primary" :disabled="loading.querying" @click="executeQuery">
            {{ loading.querying ? '查詢中...' : '執行查詢' }}
          </button>
          <button type="button" class="excel-btn excel-btn-success" :disabled="loading.exporting" @click="exportCsv">
            {{ loading.exporting ? '匯出中...' : '匯出 CSV' }}
          </button>
        </div>
      </SectionCard>

      <ErrorBanner :message="errorMessage" :dismissible="false" />
      <p v-if="successMessage" class="excel-success">{{ successMessage }}</p>

      <SectionCard>
        <template #header>
          <strong>查詢結果（{{ queryResult.total }}）</strong>
        </template>
        <DataTable :data="queryResult.rows" :loading="loading.querying">
          <DataTableColumn v-for="column in queryResult.columns" :key="column" :column-key="column" :label="column" />
          <template #cell="{ value }">{{ formatCell(value) }}</template>

          <template #empty>
            <EmptyState v-if="queryResult.rows.length === 0 && !loading.querying" text="查無資料" />
          </template>
        </DataTable>
      </SectionCard>
    </div>
  </div>
</template>
