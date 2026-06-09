<script setup lang="ts">
import { computed } from 'vue';

import { normalizeStatus, resolveOuBadgeClass } from '../../resource-shared/constants';

interface EquipmentItem {
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  EQUIPMENTASSETSSTATUS: string;
  PACKAGEGROUPNAME: string | null;
}

interface HeatmapCellSelection {
  group: string;
  packageGroupName: string;
}

const props = defineProps<{
  equipment: EquipmentItem[];
  selectedCell?: HeatmapCellSelection | null;
}>();

const emit = defineEmits<{
  'cell-select': [payload: { source: 'heatmap'; group: string; packageGroupName: string } | null];
}>();

function handleCellClick(group: string, pkg: string): void {
  emit('cell-select', { source: 'heatmap', group, packageGroupName: pkg });
}

const TIER_STYLE: Record<string, { background: string; color: string }> = {
  high:   { background: 'var(--color-token-hdcfce7)', color: 'var(--color-token-h166534)' },
  medium: { background: 'var(--color-token-hfef3c7)', color: 'var(--color-token-h92400e)' },
  low:    { background: 'var(--color-token-hfee2e2)', color: 'var(--color-token-h991b1b)' },
};
const EMPTY_STYLE = { background: 'var(--color-token-hf8fafc)', color: 'var(--color-token-h94a3b8)' };

const SCOPE_STATUSES = new Set(['PRD', 'SBY', 'UDT', 'SDT', 'EGT']);

interface CellData {
  ouPct: number | null;
  style: { background: string; color: string };
  label: string;
}

interface HeatmapRow {
  group: string;
  cells: CellData[];
}

const heatmap = computed<{ rows: HeatmapRow[]; cols: string[] }>(() => {
  const groupMeta = new Map<string, number>();
  const pkgSet = new Set<string>();
  const counts = new Map<string, { prd: number; scope: number }>();

  for (const eq of props.equipment) {
    const grp = eq.WORKCENTER_GROUP || 'UNKNOWN';
    const pkg = eq.PACKAGEGROUPNAME?.trim() || '—';
    const st = normalizeStatus(eq.EQUIPMENTASSETSSTATUS);

    if (!groupMeta.has(grp)) groupMeta.set(grp, Number(eq.WORKCENTER_GROUP_SEQ ?? 0));
    pkgSet.add(pkg);

    const key = `${grp}||${pkg}`;
    if (!counts.has(key)) counts.set(key, { prd: 0, scope: 0 });
    const c = counts.get(key)!;
    if (SCOPE_STATUSES.has(st)) {
      c.scope++;
      if (st === 'PRD') c.prd++;
    }
  }

  const sortedGroups = [...groupMeta.entries()]
    .sort((a, b) => a[1] - b[1])
    .map(([name]) => name);

  const cols = [...pkgSet].sort((a, b) => {
    if (a === '—') return 1;
    if (b === '—') return -1;
    return a.localeCompare(b);
  });

  const rows: HeatmapRow[] = sortedGroups.map((group) => ({
    group,
    cells: cols.map((pkg) => {
      const c = counts.get(`${group}||${pkg}`);
      if (!c || c.scope === 0) return { ouPct: null, style: EMPTY_STYLE, label: '—' };
      const ouPct = Math.round((c.prd / c.scope) * 1000) / 10;
      return {
        ouPct,
        style: TIER_STYLE[resolveOuBadgeClass(ouPct)],
        label: `${ouPct.toFixed(1)}%`,
      };
    }),
  }));

  return { rows, cols };
});
</script>

<template>
  <section class="heatmap-section">
    <h3 class="section-title">工作站 × 封裝群組 OU%</h3>
    <div v-if="heatmap.rows.length === 0" class="empty-hint">無資料</div>
    <div v-else class="heatmap-scroll">
      <table class="heatmap-table">
        <thead>
          <tr>
            <th class="heatmap-corner">工作站</th>
            <th v-for="col in heatmap.cols" :key="col" class="heatmap-col-header">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in heatmap.rows" :key="row.group">
            <td class="heatmap-row-label">{{ row.group }}</td>
            <td
              v-for="(cell, ci) in row.cells"
              :key="heatmap.cols[ci]"
              class="heatmap-cell"
              :class="{ 'is-selected': selectedCell?.group === row.group && selectedCell?.packageGroupName === heatmap.cols[ci] }"
              :style="cell.style"
              tabindex="0"
              role="button"
              :aria-pressed="selectedCell?.group === row.group && selectedCell?.packageGroupName === heatmap.cols[ci]"
              @click="handleCellClick(row.group, heatmap.cols[ci])"
              @keydown.enter.prevent="handleCellClick(row.group, heatmap.cols[ci])"
              @keydown.space.prevent="handleCellClick(row.group, heatmap.cols[ci])"
            >
              {{ cell.label }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
