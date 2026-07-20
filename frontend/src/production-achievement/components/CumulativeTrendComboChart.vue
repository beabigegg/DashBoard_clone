<script setup lang="ts">
/**
 * CumulativeTrendComboChart — 當月/自訂區間 cumulative trend: x-axis = date,
 * left y-axis = bar (每日產出數量, actual output for THAT day only), right
 * y-axis = line (累計達成率, the RUNNING cumulative achievement rate through
 * that day). Field-directed design (owner's explicit spec): two different-unit
 * measures over the same date axis, so a dual y-axis is the deliberate choice
 * here (mirrors the existing eap-alarm/ParetoChart.vue bar+累積% combo
 * pattern already established in this codebase) — unlike
 * PlanAchievementStackedChart.vue's single-axis 達成率 design, which stays a
 * single axis because ALL its series already share the same % unit.
 *
 * Colors resolve via resolveCssVar() (CSS custom properties in style.css
 * under .theme-production-achievement), never inline rgb()/hex — mirrors
 * PlanAchievementStackedChart.vue's convention (css-contract.md §2.4
 * chart-exception governance).
 */
import { computed } from 'vue';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';
import { formatQty } from '../utils';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent]);

const QTY_SERIES_NAME = '每日產出數量 (K)';
const RATE_SERIES_NAME = '累計達成率';

function safeNumber(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

interface Props {
  title?: string;
  categories?: string[];
  /** Daily (non-cumulative) actual output qty, parallel to `categories`. */
  qtyData?: (number | null | undefined)[];
  /** Running cumulative achievement rate, already ×100 (e.g. 87.3), parallel to `categories`. */
  rateData?: (number | null | undefined)[];
  categoryAxisName?: string;
}

const props = withDefaults(defineProps<Props>(), {
  title: '累計達成率趨勢',
  categories: () => [],
  qtyData: () => [],
  rateData: () => [],
  categoryAxisName: '日期',
});

const hasData = computed(() => props.categories.length > 0);

function resolveCssVar(varExpr: string): string {
  const match = varExpr.match(/var\((--[\w-]+)\)/);
  if (!match) return varExpr;
  return getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim();
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

function tooltipFormatter(params: AxisTooltipParam[] | AxisTooltipParam): string {
  const list = Array.isArray(params) ? params : [params];
  if (!list.length) return '';
  const categoryLabel = list[0].axisValueLabel ?? list[0].name ?? '';
  const lines = list.map((p) => {
    if (p.seriesName === RATE_SERIES_NAME) {
      const rate = safeNumber(p.value);
      return `${p.marker}${p.seriesName}: ${rate === null ? '—' : `${rate.toFixed(1)}%`}`;
    }
    return `${p.marker}${p.seriesName}: ${formatQty(p.value)}`;
  });
  return [categoryLabel, ...lines].join('<br/>');
}

const chartOption = computed(() => {
  const qtyColor = resolveCssVar('var(--pa-daily-qty-bar)');
  const rateColor = resolveCssVar('var(--pa-cumulative-rate)');
  const planColor = resolveCssVar('var(--pa-plan-line)');

  return {
    tooltip: {
      trigger: 'axis',
      confine: true,
      // Bugfix: the 累計達成率 line rides near the TOP of the plot area (it
      // hugs the 100% 計畫 markLine), and ECharts' default tooltip position
      // follows the cursor -- when hovering a bar anywhere in its upper
      // portion, the floating tooltip HTML div renders directly on top of
      // that same region and visually covers the line underneath it (this
      // is a DOM-overlap issue, not a series blur/downplay: ECharts' own
      // axisPointer highlight dispatches with `notBlur: true`, confirmed
      // against node_modules/echarts/lib/component/axisPointer/axisTrigger.js
      // -- the line itself is never actually hidden by the chart engine).
      // Anchor the tooltip near the BOTTOM of the plot area instead, clear
      // of the line's usual vertical position; `confine` then clamps it
      // horizontally so it never spills outside the chart container.
      position(point: [number, number], _params: unknown, _dom: unknown, _rect: unknown, size: { viewSize: [number, number]; contentSize: [number, number] }) {
        const y = size.viewSize[1] - size.contentSize[1] - 8;
        return [point[0], Math.max(y, 8)];
      },
      formatter: (params: AxisTooltipParam[] | AxisTooltipParam) => tooltipFormatter(params),
    },
    legend: { data: [QTY_SERIES_NAME, RATE_SERIES_NAME], bottom: 0 },
    grid: { left: 8, right: 16, top: 24, bottom: 48, containLabel: true },
    xAxis: {
      type: 'category',
      name: props.categoryAxisName,
      data: props.categories,
      axisLabel: { fontSize: 11, interval: 0, rotate: props.categories.length > 6 ? 30 : 0 },
    },
    yAxis: [
      {
        type: 'value',
        name: '每日產出數量 (K)',
        position: 'left',
        axisLabel: { formatter: (v: number) => formatQty(v) },
      },
      {
        type: 'value',
        name: '累計達成率 (%)',
        position: 'right',
        axisLabel: { formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: QTY_SERIES_NAME,
        type: 'bar',
        yAxisIndex: 0,
        data: props.qtyData.map((v) => safeNumber(v) ?? 0),
        itemStyle: { color: qtyColor },
        barMaxWidth: 40,
      },
      {
        name: RATE_SERIES_NAME,
        type: 'line',
        yAxisIndex: 1,
        data: props.rateData.map((v) => safeNumber(v)),
        connectNulls: true,
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: { color: rateColor, width: 2 },
        itemStyle: { color: rateColor },
        smooth: false,
        // Bugfix: same known ECharts issue already worked around in
        // admin-shared/components/TrendChart.vue -- hovering must not put the
        // series into an emphasis/blur state at all: on some hardware-
        // accelerated browsers the re-composite blanks the WHOLE polyline
        // (only the crosshair/tooltip survive; a data-point symbol's
        // onHoverStateChange propagates its hover state onto the whole line,
        // echarts/lib/chart/line/LineView.js `_changePolyState`). Disabling
        // emphasis outright is the proven fix (matches TrendChart.vue
        // verbatim) -- a plain `blur.lineStyle.opacity:1` style override is
        // NOT sufficient, since this is a compositor-level rendering glitch,
        // not just a low-opacity style value. The axis tooltip itself is
        // unaffected either way.
        emphasis: { disabled: true },
        markLine: {
          silent: true,
          symbol: 'none',
          label: { show: true, position: 'end', formatter: '計畫', fontSize: 11, color: planColor },
          lineStyle: { color: planColor, type: 'dashed', width: 1.5 },
          data: [{ yAxis: 100 }],
        },
      },
    ],
  };
});
</script>

<template>
  <SectionCard variant="elevated">
    <template #header>
      <h3 class="pa-card-title">{{ title }}</h3>
    </template>
    <div v-if="hasData" class="pa-chart-wrap" role="img" :aria-label="title" data-testid="pa-combo-chart">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" />
    </div>
    <div v-else class="pa-chart-empty" data-testid="pa-combo-chart-empty">目前沒有資料</div>
  </SectionCard>
</template>
