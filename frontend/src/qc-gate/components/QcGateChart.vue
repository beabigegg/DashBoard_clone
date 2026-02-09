<script setup>
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, TooltipComponent]);

const props = defineProps({
  stations: {
    type: Array,
    default: () => [],
  },
  activeFilter: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['select-segment']);

const BUCKETS = [
  { key: 'lt_6h', label: '<6hr', color: '#22c55e' },
  { key: '6h_12h', label: '6-12hr', color: '#facc15' },
  { key: '12h_24h', label: '12-24hr', color: '#fb923c' },
  { key: 'gt_24h', label: '>24hr', color: '#ef4444' },
];

function isSelected(stationName, bucketKey) {
  return (
    props.activeFilter &&
    props.activeFilter.station === stationName &&
    props.activeFilter.bucket === bucketKey
  );
}

function hasActiveFilter() {
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
        color: '#334155',
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
        color: '#334155',
        fontSize: 11,
        interval: 0,
        rotate: stationNames.length > 8 ? 30 : 0,
      },
      axisTick: {
        show: false,
      },
      axisLine: {
        lineStyle: {
          color: '#cbd5e1',
        },
      },
    },
    yAxis: {
      type: 'value',
      name: 'LOT 數',
      nameTextStyle: {
        color: '#64748b',
        padding: [0, 16, 0, 0],
      },
      axisLabel: {
        color: '#475569',
      },
      splitLine: {
        lineStyle: {
          color: '#e2e8f0',
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
        const count = Number(station?.buckets?.[bucket.key] || 0);
        const opacity = hasActiveFilter() && !isSelected(station.specname, bucket.key) ? 0.25 : 1;
        return {
          value: count,
          itemStyle: { opacity },
        };
      }),
      itemStyle: {
        borderColor: '#ffffff',
        borderWidth: 1,
      },
    })),
  };
});

function handleChartClick(params) {
  if (!params?.name || !params?.seriesId) {
    return;
  }
  emit('select-segment', {
    station: String(params.name),
    bucket: String(params.seriesId),
  });
}
</script>

<template>
  <div class="qc-gate-chart">
    <VChart
      v-if="stations.length"
      class="chart-canvas"
      :option="chartOption"
      autoresize
      @click="handleChartClick"
    />
  </div>
</template>
