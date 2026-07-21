<script setup lang="ts">
/**
 * App.vue — equipment-lookup (機台查詢)
 *
 * Root element class: theme-equipment-lookup (required for CSS scoping Rule 6)
 * No PageHeader / gradient banner — starts directly with the 查詢條件 filter
 * card, matching material-consumption/job-query/yield-alert-center/
 * production-history (portal-shell chrome handles page identification).
 *
 * Orchestrates: FilterPanel → ResultsTable
 */
import { onMounted } from 'vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import FilterPanel from './components/FilterPanel.vue';
import ResultsTable from './components/ResultsTable.vue';
import { useEquipmentLookup } from './composables/useEquipmentLookup';
import type { ListFilters } from './composables/useEquipmentLookup';

const {
  options,
  isOptionsLoading,
  optionsError,
  loadOptions,

  rows,
  pagination,
  isListLoading,
  listError,
  hasQueried,
  activeSortBy,
  activeSortDir,
  submitQuery,
  handleSort,
  handlePageChange,
  reset,

  isExporting,
  exportCsv,
} = useEquipmentLookup();

async function handleQuerySubmit(filters: ListFilters) {
  await submitQuery(filters);
}

function handleReset() {
  reset();
}

onMounted(() => {
  loadOptions();
});
</script>

<template>
  <div class="dashboard theme-equipment-lookup" data-testid="equipment-lookup-app">
    <!-- Filter options error (inline) -->
    <ErrorBanner
      :message="optionsError"
      @dismiss="optionsError = ''"
    />

    <!-- Query error -->
    <ErrorBanner
      :message="listError"
      @dismiss="listError = ''"
    />

    <!-- Initial page loading overlay (filter options) -->
    <LoadingOverlay v-if="isOptionsLoading" tier="page" />

    <!-- Filter panel -->
    <div class="ui-card filter-query-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢條件</span>
      </div>
      <div class="ui-card-body">
        <FilterPanel
          :location-options="options.locations"
          :family-options="options.families"
          :resource-name-options="options.resource_names"
          :loading="isListLoading"
          @query-submit="handleQuerySubmit"
          @reset="handleReset"
        />
      </div>
    </div>

    <!-- Results (shown after first submitted query) -->
    <div v-if="hasQueried" class="ui-card results-card">
      <div class="ui-card-header">
        <span class="ui-card-title">查詢結果</span>
      </div>
      <div class="ui-card-body results-card-body">
        <ResultsTable
          :rows="rows"
          :pagination="pagination"
          :loading="isListLoading"
          :is-exporting="isExporting"
          :active-sort-key="activeSortBy"
          :active-sort-dir="activeSortDir"
          @sort="handleSort"
          @page-change="handlePageChange"
          @export-csv="exportCsv"
        />
      </div>
    </div>

    <!-- Pre-query empty state -->
    <div
      v-else-if="!isOptionsLoading"
      class="empty-state"
      data-testid="pre-query-empty-state"
    >
      <p>請設定篩選條件後點擊「查詢」以顯示機台清單</p>
    </div>
  </div>
</template>
