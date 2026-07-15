<script setup lang="ts">
/**
 * PlanAchievementStackedChart — DailyView (當日/前日) stacked-percentage
 * chart: x-axis = PACKAGE_LF groups, D%/N% stacked series. CumulativeView
 * (當月/自訂區間) uses CumulativeTrendComboChart.vue instead (bar 每日產出數量
 * + line 累計達成率, dual axis) — this component stays daily-only but keeps
 * its generic single-series shape (no hardcoded assumption of exactly 2
 * series) since nothing here is daily-specific beyond its caller.
 *
 * Change: production-achievement-overhaul (IP-8). Y-axis is 達成率 (%) — a
 * SINGLE axis; 計畫 (target) is the y=100 reference markLine, not a second
 * scale (a dual y-axis is a dataviz anti-pattern — two different-unit
 * measures on one plot invent an alignment the data doesn't have).
 *
 * Field-directed design (owner's explicit spec, not the generic dataviz
 * default): every value is displayed as "「%」(「量」)" — e.g. "75.0%
 * (300)" — as a DIRECT LABEL on each D/N segment, not tooltip-only. This also
 * happens to fix the earlier field-reported "blank chart when no 計畫 is
 * configured yet" complaint: even a 0%-tall segment (achievement_rate is
 * null -> charted as 0) still renders its label text at the baseline, so the
 * underlying quantity stays visible with or without a target configured.
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
import { formatQty } from '../utils';

use([CanvasRenderer, BarChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent]);

const STACK_KEY = 'pa-achievement-stack';

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
 *  quantity, rather than hiding the value entirely. */
function formatPercentQty(percent: number | null | undefined, qty: number | null | undefined): string {
  const p = safeNumber(percent);
  const percentText = p === null ? '0.0' : p.toFixed(1);
  return `${percentText}% (${formatQty(qty)})`;
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
      stack: STACK_KEY,
      itemStyle: { color: resolveCssVar(s.colorVar) },
      data: s.data.map((v) => safeNumber(v) ?? 0),
      barMaxWidth: 40,
      // "% (QTY)" on EVERY segment (D班 AND N班, distinguished per the
      // field spec) — rendered at each segment's own top edge, which still
      // places the text at the baseline (visible) when that segment is 0%
      // tall, so the quantity stays readable even with no 計畫 configured.
      // A fixed per-series vertical `offset` (independent of the data value)
      // guarantees separation between adjacent series' labels even when they
      // tie exactly at 0% — without it, D班/N班 both anchor to the same
      // baseline pixel and their text renders on top of each other, unreadable.
      label: {
        show: true,
        position: 'top',
        offset: [0, -(index * 14)],
        formatter: (p: BarLabelParam) => formatPercentQty(s.data[p.dataIndex], s.qtyData?.[p.dataIndex]),
        fontSize: 10,
      },
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
