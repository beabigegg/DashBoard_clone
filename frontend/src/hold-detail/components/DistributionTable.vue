<script setup lang="ts">
interface DistRow { name: string; lots: number; qty: number; percentage: number; }

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  rows: {
    type: Array as () => DistRow[],
    default: () => [],
  },
  activeName: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle']);

function formatNumber(value: number | undefined): string {
  return Number(value || 0).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="card ui-card distribution-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">{{ title }}</div>
    </div>
    <div class="card-body ui-card-body">
      <table class="dist-table">
        <thead>
          <tr>
            <th>{{ title === 'By Workcenter' ? 'Workcenter' : 'Package' }}</th>
            <th>Lots</th>
            <th>QTY</th>
            <th>%</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="rows.length === 0">
            <td colspan="4" class="placeholder">No data</td>
          </tr>
          <tr
            v-for="row in rows"
            v-else
            :key="row.name"
            :class="{ active: activeName === row.name }"
            @click="emit('toggle', row.name)"
          >
            <td>{{ row.name || '-' }}</td>
            <td>{{ formatNumber(row.lots) }}</td>
            <td>{{ formatNumber(row.qty) }}</td>
            <td>{{ row.percentage || 0 }}%</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
