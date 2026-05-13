<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import type { StationData } from '../composables/useQcGateData';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

interface ActiveFilter {
  station: string;
  bucket: string;
}

interface Props {
  stations?: StationData[];
  activeFilter?: ActiveFilter | null;
}

const props = withDefaults(defineProps<Props>(), {
  stations: () => [],
  activeFilter: null,
});

const emit = defineEmits<{
  (e: 'select-segment', filter: ActiveFilter): void;
}>();

interface BucketDef {
  key: string;
  label: string;
  color: string;
}

const BUCKETS: BucketDef[] = [
  { key: 'lt_6h', label: '<6hr', color: 'rgb(34, 197, 94)' },
  { key: '6h_12h', label: '6-12hr', color: 'rgb(250, 204, 21)' },
  { key: '12h_24h', label: '12-24hr', color: 'rgb(251, 146, 60)' },
  { key: 'gt_24h', label: '>24hr', color: 'rgb(239, 68, 68)' },
];

function isSelected(stationName: string, bucketKey: string): boolean {
  return (
    props.activeFilter !== null &&
    props.activeFilter !== undefined &&
    props.activeFilter.station === stationName &&
    props.activeFilter.bucket === bucketKey
  );
}

function hasActiveFilter(): boolean {
  return Boolean(props.activeFilter?.station && props.activeFilter?.bucket);
}

const chartOption = computed(() => {
  const stationNames = props.stations.map((station) => station.specname);

  return {
    animationDuration: 350,
    animationDurationUpdate: 300,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
    },
    legend: {
      top: 4,
      icon: 'roundRect',
      itemHeight: 10,
      textStyle: {
        color: 'rgb(51, 65, 85)',
      },
    },
    grid: {
      left: 24,
      right: 16,
      bottom: 18,
      top: 46,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: stationNames,
      axisLabel: {
        color: 'rgb(51, 65, 85)',
        fontSize: 11,
        interval: 0,
        rotate: stationNames.length > 8 ? 30 : 0,
      },
      axisTick: {
        show: false,
      },
      axisLine: {
        lineStyle: {
          color: 'rgb(203, 213, 225)',
        },
      },
    },
    yAxis: {
      type: 'value',
      name: 'LOT 數',
      nameTextStyle: {
        color: 'rgb(100, 116, 139)',
        padding: [0, 16, 0, 0],
      },
      axisLabel: {
        color: 'rgb(71, 85, 105)',
      },
      splitLine: {
        lineStyle: {
          color: 'rgb(226, 232, 240)',
          type: 'dashed',
        },
      },
    },
    series: BUCKETS.map((bucket) => ({
      id: bucket.key,
      name: bucket.label,
      type: 'bar',
      stack: 'lots',
      color: bucket.color,
      barMaxWidth: 40,
      emphasis: {
        focus: 'series',
      },
      data: props.stations.map((station) => {
        const count = Number(station?.buckets?.[bucket.key as keyof typeof station.buckets] || 0);
        const opacity = hasActiveFilter() && !isSelected(station.specname, bucket.key) ? 0.25 : 1;
        return {
          value: count,
          itemStyle: { opacity },
        };
      }),
      itemStyle: {
        borderColor: 'rgb(255, 255, 255)',
        borderWidth: 1,
      },
    })),
  };
});

// TODO: type echarts callback
function handleChartClick(params: unknown): void {
  const p = params as { name?: unknown; seriesId?: unknown } | null | undefined;
  if (!p?.name || !p?.seriesId) {
    return;
  }
  emit('select-segment', {
    station: String(p.name),
    bucket: String(p.seriesId),
  });
}
</script>

<template>
  <div class="qc-gate-chart" role="img" aria-label="QC Gate 圖表">
    <VChart
      v-if="stations.length"
      class="chart-canvas"
      :option="chartOption"
      :autoresize="{ throttle: 100 }"
      @click="handleChartClick"
    />
  </div>
</template>
