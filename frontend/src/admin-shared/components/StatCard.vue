<template>
  <div class="stat-card">
    <div class="stat-card-value">{{ formattedValue }}</div>
    <div class="stat-card-label">{{ label }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  value: { type: [Number, String], default: '-' },
  label: { type: String, default: '' },
  unit: { type: String, default: '' },
});

const formattedValue = computed(() => {
  if (props.value === null || props.value === undefined) return '-';
  const v = typeof props.value === 'number'
    ? (Number.isInteger(props.value) ? props.value : props.value.toFixed(2))
    : props.value;
  return props.unit ? `${v} ${props.unit}` : String(v);
});
</script>
