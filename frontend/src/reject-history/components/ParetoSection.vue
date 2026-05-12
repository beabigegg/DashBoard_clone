<script setup lang="ts">
import { computed } from 'vue';

import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import type { ParetoItem } from '../useRejectHistoryDuckDB';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent]);

const DISPLAY_SCOPE_TOP20_DIMENSIONS = new Set(['type']);

const props = defineProps<{
  items?: ParetoItem[];
  selectedValues?: string[];
  selectedDates?: string[];
  metricLabel?: string;
  loading?: boolean;
  dimension?: string;
  dimensionLabel?: string;
  displayScope?: string;
}>();

const emit = defineEmits<{
  (e: 'item-toggle', value: string): void;
}>();

const selectedValueSet = computed(
  () => new Set((props.selectedValues || []).map((item: string) => String(item || '').trim())),
);

const displayItems = computed<ParetoItem[]>(() => {
  const items = Array.isArray(props.items) ? props.items : [];
  if (
    props.displayScope === 'top20'
    && DISPLAY_SCOPE_TOP20_DIMENSIONS.has(props.dimension ?? '')
  ) {
    return items.slice(0, 20);
  }
  return items;
});

const hasData = computed(() => displayItems.value.length > 0);

const showTop20Badge = computed(
  () => props.displayScope === 'top20' && DISPLAY_SCOPE_TOP20_DIMENSIONS.has(props.dimension ?? ''),
);

function isSelected(value: unknown): boolean {
  return selectedValueSet.value.has(String(value || '').trim());
}

function formatNumber(value: unknown): string {
  return Number(value || 0).toLocaleString('zh-TW');
}

function formatPct(value: unknown): string {
  return `${Number(value || 0).toFixed(2)}%`;
}

const chartOption = computed(() => {
  const items = displayItems.value;
  const metricLabel = props.metricLabel ?? '報廢量';
  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      // TODO: type — echarts formatter params is typed via echarts internals; use unknown[]
      formatter(params: unknown[]) {
        const first = (params as Array<Record<string, unknown>>)?.[0];
        const idx = Number(first?.dataIndex || 0);
        const item = items[idx] || ({} as ParetoItem);
        return [
          `<b>${item.reason || '(未填寫)'}</b>`,
          `${metricLabel}: ${formatNumber(item.metric_value || 0)}`,
          `占比: ${Number(item.pct || 0).toFixed(2)}%`,
          `累計: ${Number(item.cumPct || 0).toFixed(2)}%`,
        ].join('<br/>');
      },
    },
    legend: {
      data: [metricLabel, '累積%'],
      bottom: 0,
    },
    grid: {
      left: 52,
      right: 52,
      top: 20,
      bottom: items.length > 10 ? 110 : 96,
    },
    xAxis: {
      type: 'category',
      data: items.map((item: ParetoItem) => item.reason || '(未填寫)'),
      axisLabel: {
        interval: 0,
        rotate: items.length > 10 ? 55 : items.length > 5 ? 35 : 0,
        fontSize: items.length > 15 ? 9 : items.length > 8 ? 10 : 11,
        overflow: 'truncate',
        width: items.length > 10 ? 60 : 80,
        hideOverlap: true,
      },
    },
    yAxis: [
      {
        type: 'value',
        name: '量',
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        axisLabel: { formatter: '{value}%' },
      },
    ],
    series: [
      {
        name: metricLabel,
        type: 'bar',
        data: items.map((item: ParetoItem) => Number(item.metric_value || 0)),
        barMaxWidth: 34,
        itemStyle: {
          // TODO: type — echarts itemStyle color callback params is typed via echarts internals
          color(params: { dataIndex: number }) {
            const reason = items[params.dataIndex]?.reason || '';
            return isSelected(reason) ? 'rgb(185, 28, 28)' : 'rgb(37, 99, 235)';
          },
          borderRadius: [4, 4, 0, 0],
        },
      },
      {
        name: '累積%',
        type: 'line',
        yAxisIndex: 1,
        data: items.map((item: ParetoItem) => Number(item.cumPct || 0)),
        lineStyle: { color: 'rgb(245, 158, 11)', width: 2 },
        itemStyle: { color: 'rgb(245, 158, 11)' },
        symbolSize: 6,
      },
    ],
  };
});

function handleChartClick(params: { seriesType?: string; dataIndex: number }): void {
  if (params?.seriesType !== 'bar') {
    return;
  }
  const itemValue = displayItems.value?.[params.dataIndex]?.reason;
  if (itemValue) {
    emit('item-toggle', itemValue);
  }
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header pareto-header">
      <div class="card-title ui-card-title">
        {{ metricLabel }} vs {{ dimensionLabel }}（Pareto）
        <span v-if="showTop20Badge" class="pareto-date-badge">TOP 20</span>
        <span v-for="d in selectedDates" :key="d" class="pareto-date-badge">{{ d }}</span>
      </div>
    </div>
    <div class="card-body ui-card-body pareto-layout">
      <div class="pareto-chart-wrap" role="img" aria-label="退貨原因柏拉圖">
        <VChart :option="chartOption" :autoresize="{ throttle: 100 }" @click="handleChartClick" />
        <div v-if="!hasData && !loading" class="placeholder chart-empty">No data</div>
      </div>
      <div class="pareto-table-wrap">
        <table class="detail-table pareto-table">
          <thead>
            <tr>
              <th>{{ dimensionLabel }}</th>
              <th>{{ metricLabel }}</th>
              <th>占比</th>
              <th>累積</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in displayItems"
              :key="item.reason"
              :class="{ active: isSelected(item.reason) }"
            >
              <td>
                <button class="reason-link" type="button" @click="$emit('item-toggle', item.reason)">
                  {{ item.reason }}
                </button>
              </td>
              <td>{{ formatNumber(item.metric_value) }}</td>
              <td>{{ formatPct(item.pct) }}</td>
              <td>{{ formatPct(item.cumPct) }}</td>
            </tr>
            <tr v-if="displayItems.length === 0">
              <td colspan="4" class="placeholder">No data</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
