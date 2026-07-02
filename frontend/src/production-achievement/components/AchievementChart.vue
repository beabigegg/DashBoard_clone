<script setup lang="ts">
import { computed } from 'vue';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';
import { achievementRateForChart } from '../utils';
import type { ProductionAchievementReportRow } from '../composables/useProductionAchievement';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent]);

interface Props {
  rows?: ProductionAchievementReportRow[];
}

const props = withDefaults(defineProps<Props>(), {
  rows: () => [],
});

const hasData = computed(() => (props.rows || []).length > 0);

// Group by output_date so the chart stays readable even when shift_code /
// workcenter_group filters return many groups per day.
const chartOption = computed(() => {
  const byDate = new Map<string, { actual: number; targetSum: number; targetCount: number }>();
  for (const row of props.rows || []) {
    const key = row.output_date;
    const entry = byDate.get(key) || { actual: 0, targetSum: 0, targetCount: 0 };
    entry.actual += Number(row.actual_output_qty || 0);
    if (row.target_qty !== null && row.target_qty !== undefined) {
      entry.targetSum += Number(row.target_qty);
      entry.targetCount += 1;
    }
    byDate.set(key, entry);
  }

  const dates = [...byDate.keys()].sort();
  const actualSeries = dates.map((d) => byDate.get(d)!.actual);
  const rateSeries = dates.map((d) => {
    const entry = byDate.get(d)!;
    if (entry.targetCount === 0 || entry.targetSum === 0) return null;
    return achievementRateForChart(entry.actual / entry.targetSum);
  });

  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['實際產出', '達成率 (%)'], bottom: 0 },
    grid: { left: 8, right: 8, top: 30, bottom: 48, containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11 },
    },
    yAxis: [
      { type: 'value', name: '產出量' },
      { type: 'value', name: '達成率 (%)' },
    ],
    series: [
      {
        name: '實際產出',
        type: 'bar',
        data: actualSeries,
        itemStyle: { color: 'rgb(37, 99, 235)' },
        barMaxWidth: 24,
      },
      {
        name: '達成率 (%)',
        type: 'line',
        yAxisIndex: 1,
        data: rateSeries,
        smooth: true,
        connectNulls: false,
        lineStyle: { width: 2, color: 'rgb(22, 163, 74)' },
        itemStyle: { color: 'rgb(22, 163, 74)' },
      },
    ],
  };
});
</script>

<template>
  <SectionCard variant="elevated">
    <template #header>
      <h3 class="pa-card-title">每日達成率趨勢</h3>
    </template>
    <div v-if="hasData" class="pa-chart-wrap" role="img" aria-label="生產達成率趨勢圖" data-testid="pa-chart">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="pa-chart-empty" data-testid="pa-chart-empty">目前沒有資料</div>
  </SectionCard>
</template>
