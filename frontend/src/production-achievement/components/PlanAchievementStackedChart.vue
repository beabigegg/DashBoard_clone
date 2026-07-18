<script setup lang="ts">
/**
 * PlanAchievementStackedChart — DailyView (當日/前日) grouped-bar chart:
 * x-axis = PACKAGE_LF groups; D班 and N班 render as TWO SEPARATE side-by-side
 * bars per group (NOT stacked), each showing that shift's 班達成率 (shift
 * output ÷ shift target = CEIL(每日計畫/2), PA-21). CumulativeView (當月/自訂
 * 區間) uses CumulativeTrendComboChart.vue instead (bar 每日產出數量 + line
 * 累計達成率, dual axis) — this component stays daily-only but keeps its
 * generic multi-series shape (no hardcoded assumption of exactly 2 series).
 *
 * The filename keeps the historical "Stacked" name from the pre-PA-21 design;
 * the chart is now GROUPED side-by-side bars — stacking two independent shift
 * achievement rates has no meaningful combined height (D班 90% + N班 85% ≠ a
 * 175%-tall bar), so each shift gets its own bar compared to the 計畫 line.
 *
 * Change: production-achievement-overhaul (IP-8) + shift-achievement split.
 * Y-axis is 達成率 (%) — a SINGLE axis; 計畫 (target) is the y=100 reference
 * markLine, not a second scale (a dual y-axis is a dataviz anti-pattern — two
 * different-unit measures on one plot invent an alignment the data doesn't have).
 *
 * Field-directed design (owner's explicit spec): each bar carries a DIRECT
 * "%" label at its own top edge (e.g. "75.0%"); the underlying quantity moves
 * to the tooltip ("% (量)" per shift). A 0%-tall bar (achievement_rate is null
 * -> charted as 0) still renders its "0.0%" label at the baseline, and the
 * quantity stays visible in the tooltip and the detail table below.
 *
 * Grouped (non-stacked) series: the bars share NO `stack` key, so each shift's
 * bar independently exceeds or falls short of the y=100 `markLine` (計畫) —
 * an over-plan shift is read directly off its own bar height, never masked by
 * a sibling shift the way a shared stack would.
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
import { formatQty } from '../utils';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent]);

/** null/undefined/non-finite degrade to null, never NaN. `Number(null)`
 *  coerces to 0, so null/undefined must be checked BEFORE the numeric
 *  coercion or a genuinely-missing value silently becomes a real zero. */
function safeNumber(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** "「%」(「量」)" combined display, e.g. "75.0% (300)". A null/missing
 *  percent still renders as "0.0%" (no bar height) paired with the real
 *  quantity, rather than hiding the value entirely. Used by the tooltip. */
function formatPercentQty(percent: number | null | undefined, qty: number | null | undefined): string {
  const p = safeNumber(percent);
  const percentText = p === null ? '0.0' : p.toFixed(1);
  return `${percentText}% (${formatQty(qty)})`;
}

/** Percent-only display, e.g. "75.0%" — the DIRECT bar label (owner spec:
 *  quantity lives in the tooltip, not on the bar). A null/missing percent
 *  renders as "0.0%" so a 0%-tall bar still shows a label at the baseline. */
function formatPercent(percent: number | null | undefined): string {
  const p = safeNumber(percent);
  return `${p === null ? '0.0' : p.toFixed(1)}%`;
}

export interface StackedSeriesInput {
  name: string;
  /** A `var(--x)` CSS custom-property expression, resolved via resolveCssVar(). */
  colorVar: string;
  /** Percentage values (already ×100). null/undefined/non-finite render as 0 (no bar height). */
  data: (number | null | undefined)[];
  /**
   * Raw quantity per category, parallel to `data` (same index — e.g.
   * d_output_qty/n_output_qty for DailyView, actual_qty for the cumulative
   * trend). Combined with `data` into the "% (QTY)" label + tooltip line.
   */
  qtyData?: (number | null | undefined)[];
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

interface BarLabelParam {
  dataIndex: number;
}

interface AxisTooltipParam {
  marker: string;
  seriesName: string;
  seriesIndex: number;
  dataIndex: number;
  value: number;
  axisValueLabel?: string;
  name?: string;
}

/** Every series gets its OWN "% (QTY)" tooltip line — distinguishes D/N
 *  rather than collapsing them into one combined total. */
function tooltipFormatter(params: AxisTooltipParam[] | AxisTooltipParam, series: StackedSeriesInput[]): string {
  const list = Array.isArray(params) ? params : [params];
  if (!list.length) return '';
  const idx = list[0].dataIndex;
  const categoryLabel = list[0].axisValueLabel ?? list[0].name ?? '';
  const lines = list.map((p) => {
    const qty = series[p.seriesIndex]?.qtyData?.[idx];
    return `${p.marker}${p.seriesName}: ${formatPercentQty(p.value, qty)}`;
  });
  return [categoryLabel, ...lines].join('<br/>');
}

const chartOption = computed(() => {
  const barSeries = props.series.map((s, index) => {
    const isLast = index === props.series.length - 1;
    return {
      name: s.name,
      type: 'bar',
      // No `stack` key: D班/N班 render as SEPARATE side-by-side bars per
      // package group, each at its own 班達成率 vs the y=100 計畫 line.
      itemStyle: { color: resolveCssVar(s.colorVar) },
      data: s.data.map((v) => safeNumber(v) ?? 0),
      barMaxWidth: 40,
      // Percent-only DIRECT label at each bar's own top edge (owner spec:
      // quantity moves to the tooltip). No per-series vertical offset needed
      // now that the bars are side-by-side — each label sits above its own
      // bar and can't collide with the sibling shift's label even at 0%.
      label: {
        show: true,
        position: 'top',
        formatter: (p: BarLabelParam) => formatPercent(s.data[p.dataIndex]),
        fontSize: 10,
      },
      // Attach the y=100 計畫 markLine once, to the LAST series, so it renders
      // across the whole plot regardless of series count.
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
    tooltip: {
      trigger: 'axis',
      formatter: (params: AxisTooltipParam[] | AxisTooltipParam) => tooltipFormatter(params, props.series),
    },
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
