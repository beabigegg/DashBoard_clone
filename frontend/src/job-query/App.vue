<script setup>
import { computed, onMounted } from 'vue';

import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import FilterToolbar from '../shared-ui/components/FilterToolbar.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import SectionCard from '../shared-ui/components/SectionCard.vue';
import StatusBadge from '../shared-ui/components/StatusBadge.vue';
import { useJobQueryData } from './composables/useJobQueryData.js';

const {
  resources,
  loadingResources,
  loadingJobs,
  loadingTxn,
  exporting,
  errorMessage,
  exportMessage,
  filters,
  jobs,
  jobsColumns,
  selectedJobId,
  txnRows,
  txnColumns,
  selectedResourceCount,
  resetDateRangeToLast90Days,
  hydrateFiltersFromUrl,
  loadResources,
  queryJobs,
  loadTxn,
  exportCsv,
  getStatusTone,
} = useJobQueryData();

const resourceOptions = computed(() =>
  resources.value.map((item) => ({
    value: item.RESOURCEID,
    label: item.RESOURCENAME || item.RESOURCEID,
  })),
);

function formatCellValue(value) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
}

onMounted(async () => {
  hydrateFiltersFromUrl();
  if (!filters.startDate || !filters.endDate) {
    resetDateRangeToLast90Days();
  }
  await loadResources();
  if (filters.resourceIds.length > 0) {
    await queryJobs();
  }
});
</script>

<template>
  <div class="job-query-page dashboard theme-job-query">
    <PageHeader
      title="設備維修查詢"
      :show-refresh="false"
    />

    <div class="u-panel-stack">
      <SectionCard>
        <template #header>
          <div class="job-query-title-row">
            <strong>查詢條件</strong>
            <span class="job-query-muted">已選設備：{{ selectedResourceCount }}</span>
          </div>
        </template>

        <FilterToolbar>
          <label class="job-query-filter">
            <span>起始</span>
            <input v-model="filters.startDate" type="date" />
          </label>
          <label class="job-query-filter">
            <span>結束</span>
            <input v-model="filters.endDate" type="date" />
          </label>
          <label class="job-query-filter">
            <span>設備（複選）</span>
            <MultiSelect
              :model-value="filters.resourceIds"
              :options="resourceOptions"
              :disabled="loadingResources"
              placeholder="全部設備"
              searchable
              @update:model-value="filters.resourceIds = $event"
            />
          </label>

          <template #actions>
            <button type="button" class="job-query-btn job-query-btn-primary" :disabled="loadingJobs" @click="queryJobs">
              {{ loadingJobs ? '查詢中...' : '查詢' }}
            </button>
            <button type="button" class="job-query-btn job-query-btn-success" :disabled="exporting" @click="exportCsv">
              {{ exporting ? '匯出中...' : '匯出 CSV' }}
            </button>
          </template>
        </FilterToolbar>
      </SectionCard>

      <ErrorBanner :message="errorMessage" :dismissible="false" />
      <p v-if="exportMessage" class="job-query-success">{{ exportMessage }}</p>

      <SectionCard>
        <template #header>
          <div class="job-query-title-row">
            <strong>維修紀錄</strong>
            <span class="job-query-muted">{{ jobs.length }} 筆</span>
          </div>
        </template>

        <DataTable :data="jobs" :loading="loadingJobs">
          <DataTableColumn column-key="_action" label="操作" />
          <DataTableColumn v-for="column in jobsColumns" :key="column" :column-key="column" :label="column" />

          <template #cell="{ row, columnKey, value }">
            <template v-if="columnKey === '_action'">
              <button type="button" class="job-query-btn job-query-btn-ghost" @click="loadTxn(row.JOBID)">
                查看交易歷程
              </button>
            </template>
            <template v-else-if="columnKey === 'JOBSTATUS'">
              <StatusBadge :tone="getStatusTone(value)" :text="formatCellValue(value)" />
            </template>
            <template v-else>{{ formatCellValue(value) }}</template>
          </template>
        </DataTable>
      </SectionCard>

      <SectionCard v-if="selectedJobId">
        <template #header>
          <div class="job-query-title-row">
            <strong>交易歷程：{{ selectedJobId }}</strong>
            <span class="job-query-muted">{{ txnRows.length }} 筆</span>
          </div>
        </template>

        <DataTable :data="txnRows" :loading="loadingTxn">
          <DataTableColumn v-for="column in txnColumns" :key="column" :column-key="column" :label="column" />

          <template #cell="{ columnKey, value }">
            <template v-if="columnKey === 'JOBSTATUS' || columnKey === 'FROMJOBSTATUS'">
              <StatusBadge :tone="getStatusTone(value)" :text="formatCellValue(value)" />
            </template>
            <template v-else>{{ formatCellValue(value) }}</template>
          </template>
        </DataTable>
      </SectionCard>
    </div>
  </div>
</template>
