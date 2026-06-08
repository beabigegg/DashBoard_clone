<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps({
  data: {
    type: Object,
    default: null,
  },
  activeFilter: {
    type: Object,
    default: null,
  },
  highlightedPackage: {
    type: String,
    default: null,
  },
  highlightedStation: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['drilldown']);

const workcenters = computed(() => props.data?.workcenters || []);
const packages = computed(() => props.data?.packages || []);

interface MatrixFilterObj { workcenter?: string | null; package?: string | null; }

function normalizeFilter(filter: MatrixFilterObj | null | undefined): MatrixFilterObj | null {
  if (!filter || typeof filter !== 'object') {
    return null;
  }
  const workcenter = String(filter.workcenter || '').trim() || null;
  const pkg = String(filter.package || '').trim() || null;
  if (!workcenter && !pkg) {
    return null;
  }
  return { workcenter, package: pkg };
}

const normalizedActiveFilter = computed(() => normalizeFilter(props.activeFilter as MatrixFilterObj | null));

function isSameFilter(target: MatrixFilterObj | null | undefined): boolean {
  const current = normalizedActiveFilter.value;
  const next = normalizeFilter(target);
  if (!current && !next) {
    return true;
  }
  if (!current || !next) {
    return false;
  }
  return current.workcenter === next.workcenter && current.package === next.package;
}

function isRowActive(workcenter: string): boolean {
  const filter = normalizedActiveFilter.value;
  return Boolean(filter && filter.workcenter === workcenter && !filter.package);
}

function isCellActive(workcenter: string, pkg: string): boolean {
  const filter = normalizedActiveFilter.value;
  return Boolean(filter && filter.workcenter === workcenter && filter.package === pkg);
}

// Cross-filter dimming
const hasCrossFilter = computed(() => !!props.highlightedPackage || !!props.highlightedStation);

function isRowDimmed(workcenter: string): boolean {
  if (!props.highlightedStation) return false;
  return workcenter !== props.highlightedStation;
}

function isColDimmed(pkg: string): boolean {
  if (!props.highlightedPackage) return false;
  return pkg !== props.highlightedPackage;
}

// A cell is dimmed if its row OR its column is dimmed (cross-filter AND logic)
function isCellDimmed(workcenter: string, pkg: string): boolean {
  return isRowDimmed(workcenter) || isColDimmed(pkg);
}

function onWorkcenterClick(workcenter: string): void {
  const target: MatrixFilterObj = { workcenter, package: null };
  if (isSameFilter(target)) {
    emit('drilldown', null);
    return;
  }
  emit('drilldown', normalizeFilter(target));
}

function onCellClick(workcenter: string, pkg: string): void {
  const target: MatrixFilterObj = { workcenter, package: pkg };
  if (isSameFilter(target)) {
    emit('drilldown', null);
    return;
  }
  emit('drilldown', normalizeFilter(target));
}

function formatNumber(value: unknown): string {
  if (!value) {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function getMatrixValue(workcenter: string, pkg: string): number {
  return Number((props.data?.matrix as Record<string, Record<string, unknown>> | undefined)?.[workcenter]?.[pkg] || 0);
}
</script>

<template>
  <div v-if="workcenters.length === 0" class="placeholder">No data available</div>
  <table v-else class="matrix-table" :class="{ 'cross-filtering': hasCrossFilter }">
    <thead>
      <tr>
        <th>Workcenter</th>
        <th
          v-for="pkg in packages"
          :key="pkg"
          :class="{
            'cross-highlight': highlightedPackage === pkg,
            'cross-dim': hasCrossFilter && isColDimmed(pkg),
          }"
        >{{ pkg }}</th>
        <th class="total-col">Total</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="workcenter in workcenters"
        :key="workcenter"
        :class="{
          active: isRowActive(workcenter),
          'cross-highlight-row': highlightedStation === workcenter,
          'cross-dim-row': hasCrossFilter && isRowDimmed(workcenter),
        }"
      >
        <td
          class="clickable row-name"
          :class="{ active: isRowActive(workcenter) }"
          @click="onWorkcenterClick(workcenter)"
        >
          {{ workcenter }}
        </td>
        <td
          v-for="pkg in packages"
          :key="`${workcenter}-${pkg}`"
          class="clickable"
          :class="{
            active: isCellActive(workcenter, pkg),
            'cross-dim': hasCrossFilter && isCellDimmed(workcenter, pkg),
          }"
          @click="onCellClick(workcenter, pkg)"
        >
          {{ formatNumber(getMatrixValue(workcenter, pkg)) }}
        </td>
        <td
          class="total-col clickable"
          :class="{
            active: isRowActive(workcenter),
            'cross-dim': hasCrossFilter && isRowDimmed(workcenter),
          }"
          @click="onWorkcenterClick(workcenter)"
        >
          {{ formatNumber(data?.workcenter_totals?.[workcenter]) }}
        </td>
      </tr>

      <tr class="total-row">
        <td>Total</td>
        <td
          v-for="pkg in packages"
          :key="`total-${pkg}`"
          :class="{ 'cross-dim': hasCrossFilter && isColDimmed(pkg) }"
        >
          {{ formatNumber(data?.package_totals?.[pkg]) }}
        </td>
        <td class="total-col">{{ formatNumber(data?.grand_total) }}</td>
      </tr>
    </tbody>
  </table>
</template>
