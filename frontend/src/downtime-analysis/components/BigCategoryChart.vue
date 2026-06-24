<script setup lang="ts">
import { computed } from 'vue';
import { TreemapChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';
import type { BigCategoryRow } from '../types';
import { CATEGORY_PALETTE } from '../constants';

use([CanvasRenderer, TreemapChart, TooltipComponent]);

const props = withDefaults(defineProps<{
  rows: BigCategoryRow[];
  selectedCategory?: string | null;
  categoryColorMap?: Record<string, string>;
}>(), {
  rows: () => [],
  selectedCategory: null,
  categoryColorMap: () => ({}),
});

const emit = defineEmits<{
  'click-category': [category: string | null];
}>();

const hasData = computed(() => props.rows.length > 0);

const chartOption = computed(() => {
  const data = props.rows.map((r, i) => {
    const color = props.categoryColorMap?.[r.category] ?? CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
    const dimmed = props.selectedCategory != null && r.category !== props.selectedCategory;
    return {
      name: r.category,
      value: r.hours,
      pct: r.pct,
      itemStyle: {
        color,
        opacity: dimmed ? 0.28 : 1,
        borderColor: '#fff',
        borderWidth: 3,
        gapWidth: 3,
      },
    };
  });

  return {
    tooltip: {
      trigger: 'item',
      // TODO: type echarts callback
      formatter(params: unknown) {
        const p = params as { name: string; value: number; data: { pct: number } };
        return `<b>${p.name}</b><br/>時數: ${p.value.toFixed(1)} h<br/>佔比: ${p.data.pct.toFixed(1)}%`;
      },
    },
    series: [
      {
        type: 'treemap',
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
        visibleMin: 0,
        label: {
          show: true,
          fontSize: 13,
          fontWeight: 600,
          color: '#fff',
          textShadowBlur: 4,
          textShadowColor: 'rgba(0,0,0,0.5)',
          overflow: 'truncate',
          ellipsis: '…',
          // TODO: type echarts callback
          formatter(params: unknown) {
            const p = params as { name: string; value: number; data: { pct: number } };
            return `${p.name}\n${p.value.toFixed(1)}h  ${p.data.pct.toFixed(1)}%`;
          },
        },
        upperLabel: { show: false },
        emphasis: {
          label: { fontSize: 14, fontWeight: 700 },
          itemStyle: {
            shadowBlur: 28,
            shadowColor: 'rgba(0, 0, 0, 0.45)',
            borderColor: 'rgba(255, 255, 255, 0.9)',
            borderWidth: 4,
          },
        },
        data,
      },
    ],
  };
});

function handleChartClick(params: unknown): void {
  const p = params as { name?: string } | null;
  const name = p?.name;
  if (!name) return;
  emit('click-category', props.selectedCategory === name ? null : name);
}
</script>

<template>
  <div class="chart-card">
    <h3 class="chart-title">停機類別分佈</h3>
    <div v-if="!hasData" class="chart-empty" role="status" aria-label="無資料">
      暫無資料
    </div>
    <div v-else class="chart-container">
      <VChart
        class="chart-fill"
        :option="chartOption"
        autoresize
        role="img"
        aria-label="停機類別分佈馬賽克圖"
        @click="handleChartClick"
      />
    </div>
  </div>
</template>
