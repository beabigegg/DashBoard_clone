<script setup>
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
});

const emit = defineEmits(['select']);

const workcenters = computed(() => props.data?.workcenters || []);
const packages = computed(() => (props.data?.packages || []).slice(0, 15));

const normalizedActiveFilter = computed(() => normalizeFilter(props.activeFilter));

function normalizeFilter(filter) {
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

function isSameFilter(target) {
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

function emitSelection(target) {
  if (isSameFilter(target)) {
    emit('select', null);
    return;
  }
  emit('select', normalizeFilter(target));
}

function formatNumber(value) {
  if (!value) {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function getMatrixValue(workcenter, pkg) {
  return Number(props.data?.matrix?.[workcenter]?.[pkg] || 0);
}

function isRowActive(workcenter) {
  const filter = normalizedActiveFilter.value;
  return Boolean(filter && filter.workcenter === workcenter && !filter.package);
}

function isColumnActive(pkg) {
  const filter = normalizedActiveFilter.value;
  return Boolean(filter && filter.package === pkg && !filter.workcenter);
}

function isCellActive(workcenter, pkg) {
  const filter = normalizedActiveFilter.value;
  return Boolean(filter && filter.workcenter === workcenter && filter.package === pkg);
}

function onCellClick(workcenter, pkg) {
  emitSelection({ workcenter, package: pkg });
}

function onWorkcenterClick(workcenter) {
  emitSelection({ workcenter });
}

function onPackageClick(pkg) {
  emitSelection({ package: pkg });
}
</script>

<template>
  <div v-if="workcenters.length === 0" class="placeholder">No data available</div>
  <table v-else class="hold-matrix-table">
    <thead>
      <tr>
        <th>Workcenter</th>
        <th
          v-for="pkg in packages"
          :key="pkg"
          :class="['clickable', { active: isColumnActive(pkg) }]"
          @click="onPackageClick(pkg)"
        >
          {{ pkg }}
        </th>
        <th class="total-col clickable" @click="emitSelection(null)">Total</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="workcenter in workcenters" :key="workcenter" :class="{ active: isRowActive(workcenter) }">
        <td class="clickable row-name" @click="onWorkcenterClick(workcenter)">
          {{ workcenter }}
        </td>
        <td
          v-for="pkg in packages"
          :key="`${workcenter}-${pkg}`"
          :class="['clickable', { active: isCellActive(workcenter, pkg) }]"
          @click="onCellClick(workcenter, pkg)"
        >
          {{ formatNumber(getMatrixValue(workcenter, pkg)) }}
        </td>
        <td
          class="total-col clickable"
          :class="{ active: isRowActive(workcenter) }"
          @click="onWorkcenterClick(workcenter)"
        >
          {{ formatNumber(data?.workcenter_totals?.[workcenter]) }}
        </td>
      </tr>

      <tr class="total-row">
        <td class="clickable" @click="emitSelection(null)">Total</td>
        <td
          v-for="pkg in packages"
          :key="`total-${pkg}`"
          class="clickable"
          :class="{ active: isColumnActive(pkg) }"
          @click="onPackageClick(pkg)"
        >
          {{ formatNumber(data?.package_totals?.[pkg]) }}
        </td>
        <td class="total-col clickable" @click="emitSelection(null)">
          {{ formatNumber(data?.grand_total) }}
        </td>
      </tr>
    </tbody>
  </table>
</template>
