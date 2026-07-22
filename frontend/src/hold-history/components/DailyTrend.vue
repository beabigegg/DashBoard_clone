<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { BarChart, EffectScatterChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { graphic, use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import SectionCard from '../../shared-ui/components/SectionCard.vue';

use([CanvasRenderer, BarChart, LineChart, EffectScatterChart, GridComponent, LegendComponent, TooltipComponent]);

interface TrendDayRow {
  date?: string;
  releaseQty?: number;
  newHoldQty?: number;
  futureHoldQty?: number;
  holdQty?: number;
}

interface Props {
  days?: TrendDayRow[];
  activeDayFilter?: string;
}

const props = withDefaults(defineProps<Props>(), {
  days: () => [],
  activeDayFilter: '',
});

const emit = defineEmits<{
  'toggle-day': [value: string];
}>();

const hasData = computed(() => (props.days || []).length > 0);

// ── In-bar shimmer sweep for the active day-filter bar ───────────────────────
// A timer-driven phase (sawtooth 0 → 1, snapping back to 0 and repeating)
// drives a bright band's position WITHIN the selected bar's own gradient
// fill, so the bar itself appears to have a light shimmer pass through its
// solid body from the zero axis up to its tip, reset, and sweep again — a
// repeating one-way pass, not a back-and-forth bounce. Runs only while
// props.activeDayFilter is set — not continuously — to avoid wasted CPU.
const sweepPhase = ref(0);
let _sweepTimer: ReturnType<typeof setInterval> | null = null;

const SWEEP_PERIOD_MS = 1400;
const SWEEP_TICK_MS = 60;
const SWEEP_BAND_HALF_WIDTH = 0.16;
const SWEEP_GLOW_COLOR = 'rgba(255, 255, 255, 0.92)';

function _startSweep(): void {
  if (_sweepTimer) return;
  const start = Date.now();
  _sweepTimer = setInterval(() => {
    sweepPhase.value = ((Date.now() - start) % SWEEP_PERIOD_MS) / SWEEP_PERIOD_MS;
  }, SWEEP_TICK_MS);
}

function _stopSweep(): void {
  if (_sweepTimer) {
    clearInterval(_sweepTimer);
    _sweepTimer = null;
  }
  sweepPhase.value = 0;
}

watch(
  () => props.activeDayFilter,
  (value) => {
    if (value) _startSweep();
    else _stopSweep();
  },
  { immediate: true },
);

onBeforeUnmount(_stopSweep);

/**
 * Build a vertical linear gradient (local box coords: y=0 top, y=1 bottom)
 * for a bar's fill, with a bright glow band centered at `bandCenter`
 * (0..1, clamped) over the given base color.
 */
function buildBarSweepGradient(baseColor: string, bandCenter: number) {
  const mid = Math.max(0, Math.min(1, bandCenter));
  const lo = Math.max(0, mid - SWEEP_BAND_HALF_WIDTH);
  const hi = Math.min(1, mid + SWEEP_BAND_HALF_WIDTH);
  const stops = [{ offset: 0, color: baseColor }];
  if (lo > 0) stops.push({ offset: lo, color: baseColor });
  stops.push({ offset: mid, color: SWEEP_GLOW_COLOR });
  if (hi < 1) stops.push({ offset: hi, color: baseColor });
  stops.push({ offset: 1, color: baseColor });
  // Guard float rounding so offsets stay non-decreasing (LinearGradient requirement).
  for (let i = 1; i < stops.length; i++) {
    if (stops[i].offset < stops[i - 1].offset) stops[i].offset = stops[i - 1].offset;
  }
  return new graphic.LinearGradient(0, 0, 0, 1, stops);
}

const chartOption = computed(() => {
  const days = props.days || [];
  // Dereferenced synchronously here (not only inside a nested callback below)
  // so Vue's computed dependency tracking registers sweepPhase.value and
  // recomputes this option on every timer tick.
  const phase = sweepPhase.value;
  const dates = days.map((item) => item.date ?? '');
  const release = days.map((item) => -Math.abs(Number(item.releaseQty || 0)));
  const newHold = days.map((item) => Math.abs(Number(item.newHoldQty || 0)));
  const futureHold = days.map((item) => Math.abs(Number(item.futureHoldQty || 0)));
  const stock = days.map((item) => Number(item.holdQty || 0));

  // Which bar (if any) is the active day-filter target, and its sweep band
  // position. A bar's local gradient box has y=0 at its top and y=1 at its
  // bottom (echarts LinearGradient convention). 'New Hold' bars grow UPWARD
  // from the axis (box top = tip, box bottom = axis), so axis→tip is
  // bottom→top, i.e. offset = 1 - phase. 'Release' bars grow DOWNWARD from
  // the axis (box top = axis, box bottom = tip), so axis→tip is top→bottom,
  // i.e. offset = phase directly.
  const [activeDate, activeType] = (props.activeDayFilter || '').split(':');
  const activeIdx = activeDate ? dates.indexOf(activeDate) : -1;

  // Last day with any activity (release / new / future hold), not just carry-forward stock
  const lastStockIdx = days.reduce((acc, item, i) => {
    const active =
      Number(item.releaseQty || 0) > 0 ||
      Number(item.newHoldQty || 0) > 0 ||
      Number(item.futureHoldQty || 0) > 0;
    return active ? i : acc;
  }, -1);

  return {
    // The active-day sweep drives a full chartOption recompute on every timer
    // tick (see sweepPhase above). Without this, ECharts treats each tick's
    // setOption call as a data update on the Release/New Hold/Future Hold/On
    // Hold series too, replaying their update-transition animation from
    // scratch every ~60ms — the bars visually never finish growing while a
    // day filter is active. animationDurationUpdate: 0 makes only the shimmer
    // gradient's band position change instantly reflect; the one-time initial
    // animationDuration entrance animation on first render is unaffected.
    animationDurationUpdate: 0,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as Array<{ dataIndex?: number }>;
        const index = Number(p?.[0]?.dataIndex || 0);
        const row = days[index] || {};
        const parts = [
          `<b>${row.date || '--'}</b>`,
          `Release: ${Number(row.releaseQty || 0).toLocaleString('zh-TW')}`,
          `New Hold: ${Number(row.newHoldQty || 0).toLocaleString('zh-TW')}`,
          `Future Hold: ${Number(row.futureHoldQty || 0).toLocaleString('zh-TW')}`,
          `On Hold: ${Number(row.holdQty || 0).toLocaleString('zh-TW')}`,
        ];
        return parts.join('<br/>');
      },
    },
    legend: {
      data: ['Release', 'New Hold', 'Future Hold', 'On Hold'],
      bottom: 0,
    },
    grid: {
      left: 8,
      right: 8,
      top: 30,
      bottom: 52,
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: {
        fontSize: 11,
        interval: Math.max(Math.floor(dates.length / 12), 0),
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '增減量',
        axisLabel: {
          // TODO: type echarts callback
          formatter: (value: unknown) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
      {
        type: 'value',
        name: 'On Hold',
        axisLabel: {
          // TODO: type echarts callback
          formatter: (value: unknown) => Number(value || 0).toLocaleString('zh-TW'),
        },
      },
    ],
    series: [
      {
        name: 'Release',
        type: 'bar',
        data: release,
        itemStyle: {
          // TODO: type echarts callback
          color(params: { dataIndex: number }) {
            if (params.dataIndex === activeIdx && activeType === 'release') {
              return buildBarSweepGradient('rgb(21, 128, 61)', phase);
            }
            return 'rgb(22, 163, 74)';
          },
        },
        barMaxWidth: 18,
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(22, 163, 74, 0.8)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'New Hold',
        type: 'bar',
        stack: 'positive',
        data: newHold,
        itemStyle: {
          // TODO: type echarts callback
          color(params: { dataIndex: number }) {
            if (params.dataIndex === activeIdx && activeType === 'new') {
              return buildBarSweepGradient('rgb(153, 27, 27)', 1 - phase);
            }
            return 'rgb(220, 38, 38)';
          },
        },
        barMaxWidth: 18,
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(220, 38, 38, 0.8)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'Future Hold',
        type: 'bar',
        stack: 'positive',
        data: futureHold,
        itemStyle: { color: 'rgb(249, 115, 22)' },
        barMaxWidth: 18,
        emphasis: {
          focus: 'self',
          itemStyle: {
            shadowBlur: 18,
            shadowOffsetX: 0,
            shadowOffsetY: 0,
            shadowColor: 'rgba(249, 115, 22, 0.8)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 1.5,
          },
        },
      },
      {
        name: 'On Hold',
        type: 'line',
        yAxisIndex: 1,
        data: stock,
        smooth: true,
        lineStyle: { width: 2, color: 'rgb(37, 99, 235)' },
        itemStyle: { color: 'rgb(37, 99, 235)' },
        symbolSize: 5,
      },
      ...(lastStockIdx >= 0
        ? [
            {
              name: '_pulse',
              type: 'effectScatter',
              yAxisIndex: 1,
              symbolSize: 9,
              showEffectOn: 'render',
              rippleEffect: { brushType: 'stroke', scale: 3.5, period: 2 },
              data: [[dates[lastStockIdx], stock[lastStockIdx]]],
              itemStyle: { color: 'rgb(37, 99, 235)' },
              silent: true,
              legendHoverLink: false,
              tooltip: { show: false },
            },
          ]
        : []),
    ],
  };
});

function handleChartClick(params: { seriesType?: string; seriesName?: string; dataIndex?: number }): void {
  if (params?.seriesType !== 'bar') return;
  if (params.seriesName !== 'Release' && params.seriesName !== 'New Hold') return;
  const row = props.days?.[params.dataIndex ?? -1];
  const date = row?.date;
  if (!date) return;
  const type = params.seriesName === 'Release' ? 'release' : 'new';
  emit('toggle-day', `${date}:${type}`);
}
</script>

<template>
  <SectionCard variant="elevated" class="hh-daily-trend-card">
    <template #header>
      <h3 class="hh-card-title">Daily Trend</h3>
    </template>
    <div v-if="hasData" class="trend-chart-wrap" role="img" aria-label="Hold 每日趨勢圖">
      <VChart :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" />
    </div>
    <div v-else class="hh-chart-empty">No data</div>
  </SectionCard>
</template>
