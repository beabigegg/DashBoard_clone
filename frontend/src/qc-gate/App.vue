<script setup lang="ts">
import { computed, ref } from 'vue';

import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';
import SectionCard from '../shared-ui/components/SectionCard.vue';
import QcGateChart from './components/QcGateChart.vue';
import LotTable from './components/LotTable.vue';
import { useQcGateData } from './composables/useQcGateData';

interface ActiveFilter {
  station: string;
  bucket: string;
}

const {
  stations,
  cacheTime,
  loading,
  refreshing,
  refreshSuccess,
  refreshError,
  errorMessage,
  allLots,
  refreshNow,
} = useQcGateData();

const activeFilter = ref<ActiveFilter | null>(null);

const BUCKET_LABELS: Record<string, string> = {
  lt_6h: '<6hr',
  '6h_12h': '6-12hr',
  '12h_24h': '12-24hr',
  gt_24h: '>24hr',
};

const hasStations = computed<boolean>(() => stations.value.length > 0);

const totalLots = computed<number>(() => {
  return stations.value.reduce((sum, station) => sum + Number(station.total || 0), 0);
});

const filteredLots = computed(() => {
  if (!activeFilter.value) {
    return allLots.value;
  }

  const filter = activeFilter.value;
  return allLots.value.filter((lot) => {
    return (
      lot.step === filter.station &&
      lot.bucket === filter.bucket
    );
  });
});

const formattedCacheTime = computed<string>(() => {
  if (!cacheTime.value) {
    return '--';
  }

  const d = new Date(cacheTime.value);
  if (Number.isNaN(d.getTime())) {
    return String(cacheTime.value);
  }

  const pad = (n: number): string => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
});

const activeFilterLabel = computed<string>(() => {
  if (!activeFilter.value) {
    return '';
  }

  const bucketLabel = BUCKET_LABELS[activeFilter.value.bucket] || activeFilter.value.bucket;
  return `${activeFilter.value.station} / ${bucketLabel}`;
});

function handleChartSelect(filter: ActiveFilter): void {
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

function clearFilter(): void {
  activeFilter.value = null;
}

function handleManualRefresh(): void {
  void refreshNow();
}
</script>

<template>
  <div class="qc-gate-page theme-qc-gate">
    <PageHeader
      title="QC-GATE 狀態"
      :last-update="formattedCacheTime"
      :refreshing="loading || refreshing"
      :refresh-success="refreshSuccess"
      :refresh-error="refreshError"
      @refresh="handleManualRefresh"
    />

    <ErrorBanner :message="errorMessage" :dismissible="false" />

    <main class="qc-gate-content">
      <SectionCard variant="elevated" :class="{ 'is-refreshing': refreshing }">
        <template #header>
          <h2 class="panel-title">站點等待時間分布</h2>
          <span class="panel-hint">點擊圖表區段可篩選下方 LOT 清單</span>
        </template>

        <template v-if="!loading">
          <QcGateChart
            :stations="stations"
            :active-filter="activeFilter"
            @select-segment="handleChartSelect"
          />
          <div v-if="!hasStations" class="empty-state">目前無 QC-GATE LOT</div>
        </template>
      </SectionCard>

      <SectionCard variant="elevated" :class="{ 'is-refreshing': refreshing }">
        <template #header>
          <h2 class="panel-title">LOT 明細</h2>
          <button
            v-if="activeFilter"
            type="button"
            class="filter-indicator"
            @click="clearFilter"
          >
            篩選中：{{ activeFilterLabel }}（點擊清除）
          </button>
        </template>

        <LotTable
          :lots="filteredLots"
          :active-filter="activeFilter"
          @clear-filter="clearFilter"
        />
      </SectionCard>
    </main>

    <LoadingOverlay v-if="loading" tier="page" />
  </div>
</template>
