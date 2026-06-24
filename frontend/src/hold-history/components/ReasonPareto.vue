<script setup lang="ts">
import { computed } from 'vue';

import { BarChart, EffectScatterChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';

use([CanvasRenderer, BarChart, LineChart, EffectScatterChart, GridComponent, TooltipComponent, LegendComponent]);

interface ReasonParetoItem {
  reason?: string;
  qty?: number;
  count?: number;
  pct?: number;
  cumPct?: number;
}

interface Props {
  // TODO: type — items can come from DuckDB (typed) or server (untyped); use Record for now
  items?: Record<string, unknown>[];
  activeReason?: string;
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  activeReason: '',
});

const emit = defineEmits<{
  toggle: [reason: string];
}>();

const hasData = computed(() => (props.items || []).length > 0);

const chartOption = computed(() => {
  const items = props.items || [];
  const reasons = items.map((item) => String(item.reason || '(未填寫)'));
  const qtys = items.map((item) => Number(item.qty || 0));
  const cumPct = items.map((item) => Number(item.cumPct || 0));

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as Array<{ dataIndex?: number }>;
        const index = Number(p?.[0]?.dataIndex || 0);
        const item = items[index] || {};
        const reason = String(item.reason || '(未填寫)');
        return [
          `<b>${reason}</b>`,
          `數量: ${Number(item.qty || 0).toLocaleString('zh-TW')}`,
          `Lot 數: ${Number(item.count || 0).toLocaleString('zh-TW')}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
          `累積占比: ${Number(item.cumPct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    legend: {
      data: ['數量', '累積%'],
      bottom: 0,
    },
    grid: {
      left: 8,
      right: 8,
      top: 30,
      bottom: 100,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: reasons,
      axisLabel: {
        interval: 0,
        rotate: reasons.length > 5 ? 35 : 0,
        fontSize: 11,
        overflow: 'truncate',
        width: 92,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '數量',
        axisLabel: {
          // TODO: type echarts callback
          formatter: (value: unknown) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        axisLabel: {
          formatter: '{value}%',
        },
      },
    ],
    series: [
      {
        name: '數量',
        type: 'bar',
        data: qtys,
        itemStyle: {
          // TODO: type echarts callback
          color(params: { dataIndex: number }) {
            const reason = reasons[params.dataIndex] || '';
            return reason === props.activeReason ? 'rgb(220, 38, 38)' : 'rgb(29, 78, 216)';
          },
          borderRadius: [4, 4, 0, 0],
        },
        barMaxWidth: 36,
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(29, 78, 216, 0.75)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: '累積%',
        type: 'line',
        yAxisIndex: 1,
        data: cumPct,
        lineStyle: { color: 'rgb(245, 158, 11)', width: 2 },
        itemStyle: { color: 'rgb(245, 158, 11)' },
        symbolSize: 6,
      },
      {
        name: '_pulse',
        type: 'effectScatter',
        yAxisIndex: 1,
        symbolSize: 7,
        showEffectOn: 'render',
        rippleEffect: { brushType: 'stroke', scale: 2.8, period: 2 },
        data: reasons.map((r, i) => [r, cumPct[i]]),
        itemStyle: { color: 'rgb(245, 158, 11)' },
        silent: true,
        legendHoverLink: false,
        tooltip: { show: false },
      },
    ],
  };
});

function handleChartClick(params: { seriesType?: string; dataIndex?: number }): void {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const selected = String(props.items?.[params.dataIndex ?? -1]?.reason || '');
  if (!selected) {
    return;
  }
  emit('toggle', selected);
}
</script>

<template>
  <SectionCard variant="elevated">
    <template #header>
      <h3 class="hh-card-title">Reason Pareto</h3>
    </template>
    <div v-if="hasData" class="pareto-chart-wrap" role="img" aria-label="Hold 原因柏拉圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" />
    </div>
    <div v-else class="hh-chart-empty">No data</div>
  </SectionCard>
</template>
