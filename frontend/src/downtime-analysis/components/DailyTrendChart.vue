<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import type { DailyTrendRow } from '../types';
import { STATUS_COLORS } from '../constants';

use([CanvasRenderer, BarChart, GridComponent, TooltipComponent, LegendComponent]);

const props = withDefaults(defineProps<{
  rows: DailyTrendRow[];
  selectedStatusTypes?: string[] | null;
}>(), {
  rows: () => [],
  selectedStatusTypes: null,
});

const emit = defineEmits<{
  'click-status': [statusTypes: string[] | null];
}>();

const hasData = computed(() => props.rows.length > 0);

const chartRef = ref<InstanceType<typeof VChart> | null>(null);
const colShimmer = ref({ visible: false, style: {} as Record<string, string> });

function attachShimmerListeners(instance: unknown): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const inst = instance as any;
  inst.on('mouseover', (params: {
    componentType: string;
    name: string;
    dataIndex: number;
    seriesIndex: number;
    value: number;
  }) => {
    if (params.componentType !== 'series') return;
    const row = props.rows[params.dataIndex];
    if (!row || params.value <= 0) return;

    // Cumulative bottom of each stacked segment (stack order: UDT → SDT → EGT)
    let bottomValue = 0;
    if (params.seriesIndex === 1) bottomValue = row.udt_hours;
    if (params.seriesIndex === 2) bottomValue = row.udt_hours + row.sdt_hours;
    const topValue = bottomValue + params.value;

    const xCenter = inst.convertToPixel({ xAxisIndex: 0 }, params.name) as number;
    const yBottom = inst.convertToPixel({ yAxisIndex: 0 }, bottomValue) as number;
    const yTop = inst.convertToPixel({ yAxisIndex: 0 }, topValue) as number;

    // Estimate bar width from adjacent categories
    const dates = props.rows.map((r) => r.date);
    const nextName = params.dataIndex < dates.length - 1 ? dates[params.dataIndex + 1] : null;
    const xNext = nextName
      ? (inst.convertToPixel({ xAxisIndex: 0 }, nextName) as number)
      : xCenter + 40;
    const barW = Math.max(16, Math.abs(xNext - xCenter) * 0.65);

    colShimmer.value = {
      visible: true,
      style: {
        left: `${xCenter - barW / 2}px`,
        top: `${yTop}px`,
        width: `${barW}px`,
        height: `${Math.max(0, yBottom - yTop)}px`,
      },
    };
  });
  inst.on('mouseout', () => { colShimmer.value.visible = false; });
}

watch(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  () => (chartRef.value as any)?.chart,
  (instance) => { if (instance) attachShimmerListeners(instance); },
);

const chartOption = computed(() => {
  const dates = props.rows.map((r) => r.date);
  const udtData = props.rows.map((r) => r.udt_hours);
  const sdtData = props.rows.map((r) => r.sdt_hours);
  const egtData = props.rows.map((r) => r.egt_hours);

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as Array<{ seriesName: string; value: number; name: string }>;
        const date = p[0]?.name || '';
        const lines = p.map((item) => `${item.seriesName}: ${item.value.toFixed(1)}h`);
        return `${date}<br/>${lines.join('<br/>')}`;
      },
    },
    legend: {
      data: ['UDT', 'SDT', 'EGT'],
      top: 0,
      left: 'center',
      textStyle: { fontSize: 13, fontWeight: 600 },
      itemWidth: 22,
      itemHeight: 14,
      itemGap: 22,
      // A-1 fix: resync legend visual state from prop when chip is cleared externally
      selected: {
        UDT: !props.selectedStatusTypes || props.selectedStatusTypes.includes('UDT'),
        SDT: !props.selectedStatusTypes || props.selectedStatusTypes.includes('SDT'),
        EGT: !props.selectedStatusTypes || props.selectedStatusTypes.includes('EGT'),
      },
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '50px', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        rotate: dates.length > 14 ? 45 : 0,
        fontSize: 11,
      },
    },
    yAxis: {
      type: 'value',
      name: '小時',
      nameTextStyle: { fontSize: 11 },
    },
    series: [
      {
        name: 'UDT',
        type: 'bar',
        stack: 'total',
        data: udtData,
        itemStyle: { color: STATUS_COLORS.UDT },
        barMaxWidth: 40,
        emphasis: {
          focus: 'series',
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(239, 68, 68, 0.75)',
            borderColor: 'rgba(255, 255, 255, 0.65)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'SDT',
        type: 'bar',
        stack: 'total',
        data: sdtData,
        itemStyle: { color: STATUS_COLORS.SDT },
        barMaxWidth: 40,
        emphasis: {
          focus: 'series',
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(245, 158, 11, 0.75)',
            borderColor: 'rgba(255, 255, 255, 0.65)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'EGT',
        type: 'bar',
        stack: 'total',
        data: egtData,
        itemStyle: { color: STATUS_COLORS.EGT },
        barMaxWidth: 40,
        emphasis: {
          focus: 'series',
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(59, 130, 246, 0.75)',
            borderColor: 'rgba(255, 255, 255, 0.65)',
            borderWidth: 1.5,
          },
        },
      },
    ],
  };
});

/**
 * Legend select change: derive active status types from legend selection state.
 * Emit null when all three are active (no filter), array otherwise.
 */
function handleLegendChange(params: unknown): void {
  // TODO: type echarts callback
  const p = params as { selected?: Record<string, boolean> } | null;
  const selected = p?.selected;
  if (!selected) return;
  const active = Object.entries(selected)
    .filter(([, v]) => v)
    .map(([k]) => k);
  emit('click-status', active.length === 3 ? null : active);
}
</script>

<template>
  <div class="chart-card">
    <h3 class="chart-title">每日停機趨勢</h3>
    <div v-if="!hasData" class="chart-empty" role="status" aria-label="無資料">
      暫無資料
    </div>
    <div v-else class="chart-wrap chart-container">
      <VChart
        ref="chartRef"
        class="chart-fill"
        :option="chartOption"
        autoresize
        role="img"
        aria-label="每日停機趨勢圖"
        @legendselectchanged="handleLegendChange"
      />
      <div v-if="colShimmer.visible" class="da-col-shimmer" :style="colShimmer.style" />
    </div>
  </div>
</template>
