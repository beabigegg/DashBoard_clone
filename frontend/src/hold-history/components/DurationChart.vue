<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent]);

interface DurationItem {
  range?: string;
  qty?: number;
  count?: number;
  pct?: number;
}

interface Props {
  // TODO: type — items can come from DuckDB (typed) or server (untyped); use Record for now
  items?: Record<string, unknown>[];
  activeRange?: string;
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  activeRange: '',
});

const emit = defineEmits<{
  toggle: [range: string];
}>();

const hasData = computed(() => (props.items || []).length > 0);

const chartOption = computed(() => {
  const items = props.items || [];
  const labels = items.map((item) => String(item.range || '-'));
  const qtys = items.map((item) => Number(item.qty || 0));
  const pcts = items.map((item) => Number(item.pct || 0));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as Array<{ dataIndex?: number }>;
        const index = Number(p?.[0]?.dataIndex || 0);
        const item = items[index] || {};
        return [
          `<b>${String(item.range || '-')}</b>`,
          `數量: ${Number(item.qty || 0).toLocaleString('zh-TW')}`,
          `Lot 數: ${Number(item.count || 0).toLocaleString('zh-TW')}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    grid: {
      left: 8,
      right: 8,
      top: 14,
      bottom: 24,
      containLabel: true,
    },
    xAxis: {
      type: 'value',
      axisLabel: {
        // TODO: type echarts callback
        formatter: (value: unknown) => Number(value || 0).toLocaleString('zh-TW'),
      },
    },
    yAxis: {
      type: 'category',
      data: labels,
    },
    series: [
      {
        type: 'bar',
        data: qtys,
        barMaxWidth: 26,
        itemStyle: {
          // TODO: type echarts callback
          color(params: { dataIndex: number }) {
            const range = labels[params.dataIndex] || '';
            return range === props.activeRange ? 'rgb(220, 38, 38)' : 'rgb(124, 58, 237)';
          },
          borderRadius: [0, 4, 4, 0],
        },
        label: {
          show: true,
          position: 'right',
          // TODO: type echarts callback
          formatter(params: { dataIndex: number; value: unknown }) {
            const pct = Number(pcts[params.dataIndex] || 0).toFixed(1);
            const qty = Number(params.value || 0).toLocaleString('zh-TW');
            return `${qty} (${pct}%)`;
          },
          fontSize: 11,
        },
      },
    ],
  };
});

function handleChartClick(params: { seriesType?: string; dataIndex?: number }): void {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const selected = String(props.items?.[params.dataIndex ?? -1]?.range || '');
  if (!selected) {
    return;
  }
  emit('toggle', selected);
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">Hold Duration Distribution</div>
    </div>
    <div class="card-body ui-card-body">
      <div v-if="hasData" class="duration-chart-wrap" role="img" aria-label="Hold 時長分佈圖">
        <VChart :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" />
      </div>
      <div v-else class="placeholder">No data</div>
    </div>
  </section>
</template>
