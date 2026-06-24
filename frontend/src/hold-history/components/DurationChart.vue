<script setup lang="ts">
import { computed } from 'vue';

import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';

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
      right: 140,
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
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(124, 58, 237, 0.75)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
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
  <SectionCard variant="elevated">
    <template #header>
      <h3 class="hh-card-title">Hold Duration Distribution</h3>
    </template>
    <div v-if="hasData" class="duration-chart-wrap" role="img" aria-label="Hold 時長分佈圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" />
    </div>
    <div v-else class="hh-chart-empty">No data</div>
  </SectionCard>
</template>
