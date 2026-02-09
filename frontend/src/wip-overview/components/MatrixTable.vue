<script setup>
import { computed } from 'vue';

const props = defineProps({
  data: {
    type: Object,
    default: null,
  },
});

const emit = defineEmits(['drilldown']);

const workcenters = computed(() => props.data?.workcenters || []);
const packages = computed(() => (props.data?.packages || []).slice(0, 15));

function formatNumber(value) {
  if (!value) {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function getMatrixValue(workcenter, pkg) {
  return props.data?.matrix?.[workcenter]?.[pkg] || 0;
}
</script>

<template>
  <div v-if="workcenters.length === 0" class="placeholder">No data available</div>
  <table v-else class="matrix-table">
    <thead>
      <tr>
        <th>Workcenter</th>
        <th v-for="pkg in packages" :key="pkg">{{ pkg }}</th>
        <th class="total-col">Total</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="workcenter in workcenters" :key="workcenter">
        <td class="clickable" @click="emit('drilldown', workcenter)">{{ workcenter }}</td>
        <td v-for="pkg in packages" :key="`${workcenter}-${pkg}`">
          {{ formatNumber(getMatrixValue(workcenter, pkg)) }}
        </td>
        <td class="total-col">{{ formatNumber(data?.workcenter_totals?.[workcenter]) }}</td>
      </tr>

      <tr class="total-row">
        <td>Total</td>
        <td v-for="pkg in packages" :key="`total-${pkg}`">
          {{ formatNumber(data?.package_totals?.[pkg]) }}
        </td>
        <td class="total-col">{{ formatNumber(data?.grand_total) }}</td>
      </tr>
    </tbody>
  </table>
</template>
