<script setup>
import { computed, onMounted } from 'vue';

import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import FilterToolbar from '../shared-ui/components/FilterToolbar.vue';
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
  <div class="job-query-page u-content-shell theme-job-query">
    <header class="job-query-header">
      <h1>設備維修查詢</h1>
    </header>

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

      <p v-if="errorMessage" class="job-query-error">{{ errorMessage }}</p>
      <p v-if="exportMessage" class="job-query-success">{{ exportMessage }}</p>

      <SectionCard>
        <template #header>
          <div class="job-query-title-row">
            <strong>維修紀錄</strong>
            <span class="job-query-muted">{{ jobs.length }} 筆</span>
          </div>
        </template>

        <div v-if="loadingJobs" class="job-query-empty">查詢中...</div>
        <div v-else-if="jobs.length === 0" class="job-query-empty">目前無資料</div>
        <div v-else class="job-query-table-wrap">
          <table class="job-query-table">
            <thead>
              <tr>
                <th>操作</th>
                <th v-for="column in jobsColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in jobs" :key="row.JOBID || `${row.RESOURCENAME}-${row.CREATEDATE}`">
                <td>
                  <button type="button" class="job-query-btn job-query-btn-ghost" @click="loadTxn(row.JOBID)">
                    查看交易歷程
                  </button>
                </td>
                <td v-for="column in jobsColumns" :key="column">
                  <StatusBadge
                    v-if="column === 'JOBSTATUS'"
                    :tone="getStatusTone(row[column])"
                    :text="formatCellValue(row[column])"
                  />
                  <span v-else>{{ formatCellValue(row[column]) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard v-if="selectedJobId">
        <template #header>
          <div class="job-query-title-row">
            <strong>交易歷程：{{ selectedJobId }}</strong>
            <span class="job-query-muted">{{ txnRows.length }} 筆</span>
          </div>
        </template>

        <div v-if="loadingTxn" class="job-query-empty">載入交易歷程中...</div>
        <div v-else-if="txnRows.length === 0" class="job-query-empty">無交易歷程資料</div>
        <div v-else class="job-query-table-wrap">
          <table class="job-query-table">
            <thead>
              <tr>
                <th v-for="column in txnColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in txnRows" :key="row.JOBTXNHISTORYID || row.TXNDATE">
                <td v-for="column in txnColumns" :key="column">
                  <StatusBadge
                    v-if="column === 'JOBSTATUS' || column === 'FROMJOBSTATUS'"
                    :tone="getStatusTone(row[column])"
                    :text="formatCellValue(row[column])"
                  />
                  <span v-else>{{ formatCellValue(row[column]) }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  </div>
</template>
