<script setup>
import { computed, ref } from 'vue';

import QcGateChart from './components/QcGateChart.vue';
import LotTable from './components/LotTable.vue';
import { useQcGateData } from './composables/useQcGateData.js';

const {
  stations,
  cacheTime,
  loading,
  refreshing,
  errorMessage,
  allLots,
  refreshNow,
} = useQcGateData();

const activeFilter = ref(null);

const BUCKET_LABELS = {
  lt_6h: '<6hr',
  '6h_12h': '6-12hr',
  '12h_24h': '12-24hr',
  gt_24h: '>24hr',
};

const hasStations = computed(() => stations.value.length > 0);

const totalLots = computed(() => {
  return stations.value.reduce((sum, station) => sum + Number(station.total || 0), 0);
});

const filteredLots = computed(() => {
  if (!activeFilter.value) {
    return allLots.value;
  }

  return allLots.value.filter((lot) => {
    return (
      lot.step === activeFilter.value.station &&
      lot.bucket === activeFilter.value.bucket
    );
  });
});

const formattedCacheTime = computed(() => {
  if (!cacheTime.value) {
    return '--';
  }

  const date = new Date(cacheTime.value);
  if (Number.isNaN(date.getTime())) {
    return String(cacheTime.value);
  }

  return date.toLocaleString('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
});

const activeFilterLabel = computed(() => {
  if (!activeFilter.value) {
    return '';
  }

  const bucketLabel = BUCKET_LABELS[activeFilter.value.bucket] || activeFilter.value.bucket;
  return `${activeFilter.value.station} / ${bucketLabel}`;
});

function handleChartSelect(filter) {
  if (!filter?.station || !filter?.bucket) {
    return;
  }

  if (
    activeFilter.value &&
    activeFilter.value.station === filter.station &&
    activeFilter.value.bucket === filter.bucket
  ) {
    activeFilter.value = null;
    return;
  }

  activeFilter.value = filter;
}

function clearFilter() {
  activeFilter.value = null;
}

function handleManualRefresh() {
  void refreshNow();
}
</script>

<template>
  <div class="qc-gate-page theme-qc-gate">
    <header class="qc-gate-header">
      <div>
        <h1>QC-GATE 狀態</h1>
        <p class="header-subtitle">即時監控各 QC-GATE 站點的在製 LOT 與等待時間</p>
      </div>
      <div class="header-meta">
        <div class="meta-row">
          <span class="meta-label">快照時間</span>
          <span class="meta-value">{{ formattedCacheTime }}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">總 LOT</span>
          <span class="meta-value">{{ totalLots.toLocaleString('zh-TW') }}</span>
        </div>
        <button
          type="button"
          class="refresh-button"
          :disabled="loading || refreshing"
          @click="handleManualRefresh"
        >
          {{ refreshing ? '更新中...' : '重新整理' }}
        </button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <main class="qc-gate-content">
      <section class="panel chart-panel" :class="{ 'is-refreshing': refreshing }">
        <div class="panel-header">
          <h2>站點等待時間分布</h2>
          <span class="panel-hint">點擊圖表區段可篩選下方 LOT 清單</span>
        </div>

        <div v-if="loading" class="loading-state">資料載入中...</div>

        <template v-else>
          <QcGateChart
            :stations="stations"
            :active-filter="activeFilter"
            @select-segment="handleChartSelect"
          />
          <div v-if="!hasStations" class="empty-state">目前無 QC-GATE LOT</div>
        </template>
      </section>

      <section class="panel table-panel" :class="{ 'is-refreshing': refreshing }">
        <div class="panel-header">
          <h2>LOT 明細</h2>
          <button
            v-if="activeFilter"
            type="button"
            class="filter-indicator"
            @click="clearFilter"
          >
            篩選中：{{ activeFilterLabel }}（點擊清除）
          </button>
        </div>

        <LotTable
          :lots="filteredLots"
          :active-filter="activeFilter"
          @clear-filter="clearFilter"
        />
      </section>
    </main>
  </div>
</template>
