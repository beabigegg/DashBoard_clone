<script setup>
const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  rows: {
    type: Array,
    default: () => [],
  },
  activeName: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(['toggle']);

function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-TW');
}
</script>

<template>
  <section class="card distribution-card">
    <div class="card-header">
      <div class="card-title">{{ title }}</div>
    </div>
    <div class="card-body">
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
