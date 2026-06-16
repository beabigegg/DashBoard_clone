<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import LoadingSpinner from '../shared-ui/components/LoadingSpinner.vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import FilterToolbar from '../shared-ui/components/FilterToolbar.vue';
import SectionCard from '../shared-ui/components/SectionCard.vue';
import StatusBadge from '../shared-ui/components/StatusBadge.vue';
import { useJobQueryData } from './composables/useJobQueryData';

const ROWS_PER_PAGE = 25;

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

// ── Renderless component to trigger loadTxn when expand slot mounts ──
const ExpandTxnLoader = {
  props: {
    jobId: { type: String, required: true as const },
    loadFn: { type: Function as unknown as () => (id: string) => Promise<void> | void, required: true as const },
  },
  mounted(this: { jobId: string; loadFn: (id: string) => Promise<void> | void }) {
    if (this.jobId && this.loadFn) this.loadFn(this.jobId);
  },
  render() { return null; },
};

// ── Client-side pagination ──
const currentPage = ref(1);

const pagedJobs = computed(() => {
  const start = (currentPage.value - 1) * ROWS_PER_PAGE;
  return jobs.value.slice(start, start + ROWS_PER_PAGE);
});

const jobsPagination = computed(() => {
  const total = jobs.value.length;
  const totalPages = Math.max(1, Math.ceil(total / ROWS_PER_PAGE));
  return {
    page: currentPage.value,
    totalPages,
    infoText: `共 ${total} 筆`,
  };
});

function handleJobsPageChange(page: number): void {
  currentPage.value = page;
}

// Reset to page 1 when query completes
const originalQueryJobs = queryJobs;
async function wrappedQueryJobs() {
  currentPage.value = 1;
  return originalQueryJobs();
}

const resourceOptions = computed(() =>
  resources.value.map((item) => ({
    value: item.RESOURCEID,
    label: item.RESOURCENAME || item.RESOURCEID,
  })),
);

function formatCellValue(value: unknown): string {
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
    await wrappedQueryJobs();
  }
});
</script>

<template>
  <div class="job-query-page dashboard theme-job-query">
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
            <button type="button" class="job-query-btn job-query-btn-primary" :disabled="loadingJobs" @click="wrappedQueryJobs">
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

        <DataTable
          :data="pagedJobs"
          :loading="loadingJobs"
          :pagination="jobsPagination"
          @page-change="handleJobsPageChange"
        >
          <DataTableColumn v-for="column in jobsColumns" :key="column" :column-key="column" :label="column" />

          <template #empty>
            <EmptyState text="目前無資料" />
          </template>

          <template #cell="{ row, columnKey, value }">
            <template v-if="columnKey === 'JOBSTATUS'">
              <StatusBadge :tone="getStatusTone(value)" :text="formatCellValue(value)" />
            </template>
            <template v-else>{{ formatCellValue(value) }}</template>
          </template>

          <template #expand="{ row }">
            <ExpandTxnLoader :job-id="row.JOBID" :load-fn="loadTxn" />
            <div class="job-query-txn-expand">
              <div class="job-query-txn-header">
                <strong>交易歷程：{{ row.JOBID }}</strong>
                <LoadingSpinner v-if="loadingTxn && selectedJobId === row.JOBID" size="sm" />
              </div>
              <table v-if="selectedJobId === row.JOBID && txnRows.length > 0" class="job-query-txn-table">
                <thead>
                  <tr>
                    <th v-for="col in txnColumns" :key="col">{{ col }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(txn, ti) in txnRows" :key="ti">
                    <td v-for="col in txnColumns" :key="col">
                      <template v-if="col === 'JOBSTATUS' || col === 'FROMJOBSTATUS'">
                        <StatusBadge :tone="getStatusTone(txn[col])" :text="formatCellValue(txn[col])" />
                      </template>
                      <template v-else>{{ formatCellValue(txn[col]) }}</template>
                    </td>
                  </tr>
                </tbody>
              </table>
              <p v-else-if="selectedJobId === row.JOBID && !loadingTxn" class="job-query-muted">無交易歷程</p>
            </div>
          </template>
        </DataTable>
      </SectionCard>
    </div>

    <LoadingOverlay v-if="loadingJobs" tier="page" />
  </div>
</template>
