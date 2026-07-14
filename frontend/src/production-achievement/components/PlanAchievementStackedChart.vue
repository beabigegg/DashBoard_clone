<script setup lang="ts">
/**
 * PlanAchievementStackedChart — shared stacked-percentage chart for both
 * DailyView (x-axis = PACKAGE_LF groups, D%/N% stacked series) and
 * CumulativeView-trend (x-axis = dates, one aggregate-rate series).
 *
 * Change: production-achievement-overhaul (IP-8). Replaces AchievementChart.vue
 * (hard cutover, no flag — design.md § Migration/Rollback).
 *
 * REAL (non-normalized) stacked series: every series shares one `stack` key
 * with ECharts' default summing behaviour — segments can visually exceed the
 * y=100 `markLine` (計畫) for an over-plan combination. Deliberately NOT
 * ECharts' normalize-to-100 stacking, which would silently cap that signal.
 *
 * Colors resolve via resolveCssVar() (CSS custom properties defined in
 * style.css under .theme-production-achievement), never inline rgb()/hex —
 * mirrors resource-history/components/StackedChart.vue's established
 * convention (css-contract.md §2.4 chart-exception governance).
 */
import { computed } from 'vue';
import { BarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent]);

const STACK_KEY = 'pa-achievement-stack';

/**
 * Data values here are ALREADY percentages (×100 applied by the caller — see
 * useProductionAchievementDuckDB.ts's achievement_rate fields, PA-12/PA-13).
 * This guard only degrades null/undefined/non-finite to 0 (no bar height);
 * it must NOT multiply again (unlike utils.ts's achievementRateForChart(),
 * which scales a 0..1 ratio -- not applicable here).
 */
function safePercent(value: number | null | undefined): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export interface StackedSeriesInput {
  name: string;
  /** A `var(--x)` CSS custom-property expression, resolved via resolveCssVar(). */
  colorVar: string;
  /** Percentage values (already ×100). null/undefined/non-finite render as 0 (no bar height). */
  data: (number | null | undefined)[];
}

interface Props {
  title?: string;
  categories?: string[];
  series?: StackedSeriesInput[];
  categoryAxisName?: string;
  valueAxisName?: string;
}

const props = withDefaults(defineProps<Props>(), {
  title: '達成率趨勢',
  categories: () => [],
  series: () => [],
  categoryAxisName: '',
  valueAxisName: '達成率 (%)',
});

const hasData = computed(() => props.categories.length > 0 && props.series.length > 0);

function resolveCssVar(varExpr: unknown): string {
  const match = String(varExpr).match(/var\((--[\w-]+)\)/);
  if (!match) return String(varExpr);
  return getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim();
}

const chartOption = computed(() => {
  const barSeries = props.series.map((s, index) => {
    const isLast = index === props.series.length - 1;
    return {
      name: s.name,
      type: 'bar',
      stack: STACK_KEY,
      itemStyle: { color: resolveCssVar(s.colorVar) },
      data: s.data.map((v) => safePercent(v)),
      barMaxWidth: 40,
      // Attach the y=100 計畫 markLine once, to the LAST stacked series, so it
      // visually renders at the top of the stack regardless of series count.
      ...(isLast
        ? {
            markLine: {
              silent: true,
              symbol: 'none',
              label: { show: true, position: 'end', formatter: '計畫', fontSize: 11, color: resolveCssVar('var(--pa-plan-line)') },
              lineStyle: { color: resolveCssVar('var(--pa-plan-line)'), type: 'dashed', width: 1.5 },
              data: [{ yAxis: 100 }],
            },
          }
        : {}),
    };
  });

  return {
    tooltip: { trigger: 'axis', valueFormatter: (v: number) => `${Number(v).toFixed(1)}%` },
    legend: { data: props.series.map((s) => s.name), bottom: 0 },
    grid: { left: 8, right: 16, top: 24, bottom: 48, containLabel: true },
    xAxis: {
      type: 'category',
      name: props.categoryAxisName,
      data: props.categories,
      axisLabel: { fontSize: 11, interval: 0, rotate: props.categories.length > 6 ? 30 : 0 },
    },
    yAxis: {
      type: 'value',
      name: props.valueAxisName,
      axisLabel: { formatter: '{value}%' },
    },
    series: barSeries,
  };
});
</script>

<template>
  <SectionCard variant="elevated">
    <template #header>
      <h3 class="pa-card-title">{{ title }}</h3>
    </template>
    <div v-if="hasData" class="pa-chart-wrap" role="img" :aria-label="title" data-testid="pa-chart">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="pa-chart-empty" data-testid="pa-chart-empty">目前沒有資料</div>
  </SectionCard>
</template>
