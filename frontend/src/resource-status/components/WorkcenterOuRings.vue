<script setup lang="ts">
import { computed } from 'vue';

import { PieChart } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import VChart from 'vue-echarts';

import { MATRIX_STATUS_COLUMNS, STATUS_DISPLAY_MAP, normalizeStatus, resolveOuBadgeClass } from '../../resource-shared/constants';

use([CanvasRenderer, PieChart, TooltipComponent]);

interface EquipmentItem {
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  EQUIPMENTASSETSSTATUS: string;
}

interface RingSelection {
  group: string;
  status: string;
}

const props = defineProps<{
  equipment: EquipmentItem[];
  selection?: RingSelection | null;
}>();

const emit = defineEmits<{
  'chart-select': [payload: { source: 'ring'; group: string; status: string } | null];
}>();

// STATUS_DISPLAY_MAP maps 'PRD' -> '生產' etc.; reverse-map for click
const DISPLAY_TO_STATUS: Record<string, string> = Object.fromEntries(
  Object.entries(STATUS_DISPLAY_MAP).map(([k, v]) => [v, k])
);

function handleChartClick(group: string, params: { name?: string }): void {
  const displayName = params.name || '';
  const status = DISPLAY_TO_STATUS[displayName] || displayName;
  if (!status || !group) return;
  emit('chart-select', { source: 'ring', group, status });
}

const CHART_COLORS: Record<string, string> = {
  PRD: '#22c55e',
  SBY: '#3b82f6',
  UDT: '#ef4444',
  SDT: '#f59e0b',
  EGT: '#8b5cf6',
  NST: '#64748b',
  OTHER: '#94a3b8',
};

const OU_TEXT_COLORS = { high: '#166534', medium: '#92400e', low: '#991b1b' } as const;

interface RingData {
  group: string;
  seq: number;
  ouPct: number;
  ouClass: 'high' | 'medium' | 'low';
  counts: Record<string, number>;
}

const rings = computed<RingData[]>(() => {
  const map = new Map<string, { seq: number; counts: Record<string, number> }>();

  for (const eq of props.equipment) {
    const grp = eq.WORKCENTER_GROUP || 'UNKNOWN';
    if (!map.has(grp)) {
      map.set(grp, {
        seq: Number(eq.WORKCENTER_GROUP_SEQ ?? 0),
        counts: Object.fromEntries(MATRIX_STATUS_COLUMNS.map((s) => [s, 0])),
      });
    }
    const entry = map.get(grp)!;
    const st = normalizeStatus(eq.EQUIPMENTASSETSSTATUS);
    entry.counts[st] = (entry.counts[st] ?? 0) + 1;
  }

  return [...map.entries()]
    .sort((a, b) => a[1].seq - b[1].seq)
    .map(([group, { seq, counts }]) => {
      const scope =
        (counts.PRD ?? 0) +
        (counts.SBY ?? 0) +
        (counts.UDT ?? 0) +
        (counts.SDT ?? 0) +
        (counts.EGT ?? 0);
      const ouPct = scope > 0 ? Math.round(((counts.PRD ?? 0) / scope) * 1000) / 10 : 0;
      return { group, seq, ouPct, ouClass: resolveOuBadgeClass(ouPct), counts };
    });
});

function ringOption(ring: RingData) {
  const isGroupSelected = props.selection?.group === ring.group;

  const data = MATRIX_STATUS_COLUMNS.filter((s) => (ring.counts[s] ?? 0) > 0).map((s) => {
    const displayName = STATUS_DISPLAY_MAP[s] || s;
    const isSegmentSelected = isGroupSelected && props.selection?.status === s;
    const itemStyle: Record<string, unknown> = { color: CHART_COLORS[s] ?? '#94a3b8' };
    if (isGroupSelected) {
      itemStyle.opacity = isSegmentSelected ? 1.0 : 0.4;
    }
    return { value: ring.counts[s], name: displayName, itemStyle };
  });

  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 台 ({d}%)' },
    series: [
      {
        type: 'pie',
        radius: ['56%', '82%'],
        data: data.length ? data : [{ value: 1, name: '無資料', itemStyle: { color: '#e2e8f0' } }],
        label: { show: false },
        labelLine: { show: false },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.15)' } },
      },
    ],
  };
}
</script>

<template>
  <section class="rings-section">
    <h3 class="section-title">工作站 OU% 分佈</h3>
    <div v-if="rings.length === 0" class="empty-hint">無設備資料</div>
    <div v-else class="rings-strip">
      <div v-for="ring in rings" :key="ring.group" class="ring-card">
        <div class="ring-chart-wrap">
          <VChart :option="ringOption(ring)" autoresize class="ring-chart" @click="(params: { name?: string }) => handleChartClick(ring.group, params)" />
          <div class="ring-center" :style="{ color: OU_TEXT_COLORS[ring.ouClass] }">
            <span class="ring-pct">{{ ring.ouPct.toFixed(1) }}%</span>
            <span class="ring-ou-label">OU</span>
          </div>
        </div>
        <div class="ring-group-name">{{ ring.group }}</div>
        <div class="ring-legend">
          <template v-for="s in MATRIX_STATUS_COLUMNS" :key="s">
            <span v-if="(ring.counts[s] ?? 0) > 0" class="legend-chip">
              <span class="legend-dot" :style="{ background: CHART_COLORS[s] }"></span>
              <span class="legend-abbr">{{ s }}</span>
              <span class="legend-num">{{ ring.counts[s] }}</span>
            </span>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>
