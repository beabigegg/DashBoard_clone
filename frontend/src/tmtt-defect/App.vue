<script setup>
import { computed } from 'vue';

import FilterToolbar from '../shared-ui/components/FilterToolbar.vue';
import SectionCard from '../shared-ui/components/SectionCard.vue';
import StatusBadge from '../shared-ui/components/StatusBadge.vue';
import TmttChartCard from './components/TmttChartCard.vue';
import TmttDetailTable from './components/TmttDetailTable.vue';
import TmttKpiCards from './components/TmttKpiCards.vue';
import { useTmttDefectData } from './composables/useTmttDefectData.js';

const {
  startDate,
  endDate,
  loading,
  errorMessage,
  hasData,
  kpi,
  charts,
  dailyTrend,
  filteredRows,
  totalCount,
  filteredCount,
  activeFilter,
  sortState,
  queryData,
  setFilter,
  clearFilter,
  toggleSort,
  exportCsv,
} = useTmttDefectData();

const paretoCharts = [
  { key: 'by_workflow', field: 'WORKFLOW', title: '依 WORKFLOW' },
  { key: 'by_package', field: 'PRODUCTLINENAME', title: '依 PACKAGE' },
  { key: 'by_type', field: 'PJ_TYPE', title: '依 TYPE' },
  { key: 'by_tmtt_machine', field: 'TMTT_EQUIPMENTNAME', title: '依 TMTT 機台' },
  { key: 'by_mold_machine', field: 'MOLD_EQUIPMENTNAME', title: '依 MOLD 機台' },
];

const detailCountLabel = computed(() => {
  if (!activeFilter.value) {
    return `${filteredCount.value} 筆`;
  }
  return `${filteredCount.value} / ${totalCount.value} 筆`;
});
</script>

<template>
  <div class="tmtt-page u-content-shell">
    <header class="tmtt-header">
      <h1>TMTT 印字與腳型不良分析</h1>
      <p>Legacy rewrite exemplar：Vue 元件化 + Shared UI + Tailwind token layer</p>
    </header>

    <div class="u-panel-stack">
      <SectionCard>
        <template #header>
          <div class="tmtt-block-title">查詢條件</div>
        </template>

        <FilterToolbar>
          <label class="tmtt-field">
            <span>起始日期</span>
            <input v-model="startDate" type="date" />
          </label>
          <label class="tmtt-field">
            <span>結束日期</span>
            <input v-model="endDate" type="date" />
          </label>

          <template #actions>
            <button type="button" class="tmtt-btn tmtt-btn-primary" :disabled="loading" @click="queryData">
              {{ loading ? '查詢中...' : '查詢' }}
            </button>
            <button type="button" class="tmtt-btn tmtt-btn-success" :disabled="loading" @click="exportCsv">
              匯出 CSV
            </button>
          </template>
        </FilterToolbar>
      </SectionCard>

      <p v-if="errorMessage" class="tmtt-error-banner">{{ errorMessage }}</p>

      <template v-if="hasData">
        <TmttKpiCards :kpi="kpi" />

        <div class="tmtt-chart-grid">
          <TmttChartCard
            v-for="config in paretoCharts"
            :key="config.key"
            :title="config.title"
            mode="pareto"
            :field="config.field"
            :selected-value="activeFilter?.value || ''"
            :data="charts[config.key] || []"
            @select="setFilter"
          />

          <TmttChartCard
            title="每日印字不良率趨勢"
            mode="print-trend"
            :data="dailyTrend"
            line-label="印字不良率"
            line-color="#ef4444"
          />

          <TmttChartCard
            title="每日腳型不良率趨勢"
            mode="lead-trend"
            :data="dailyTrend"
            line-label="腳型不良率"
            line-color="#f59e0b"
          />
        </div>

        <SectionCard>
          <template #header>
            <div class="tmtt-detail-header">
              <div>
                <strong>明細清單</strong>
                <span class="tmtt-detail-count">({{ detailCountLabel }})</span>
              </div>
              <div class="tmtt-detail-actions">
                <StatusBadge
                  v-if="activeFilter"
                  tone="warning"
                  :text="activeFilter.label"
                />
                <button
                  v-if="activeFilter"
                  type="button"
                  class="tmtt-btn tmtt-btn-ghost"
                  @click="clearFilter"
                >
                  清除篩選
                </button>
              </div>
            </div>
          </template>

          <TmttDetailTable :rows="filteredRows" :sort-state="sortState" @sort="toggleSort" />
        </SectionCard>
      </template>

      <SectionCard v-else>
        <div class="tmtt-empty-state">
          <p>請選擇日期範圍後點擊「查詢」。</p>
        </div>
      </SectionCard>
    </div>
  </div>
</template>
