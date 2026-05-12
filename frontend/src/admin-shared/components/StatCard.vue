<template>
  <div class="stat-card">
    <div class="stat-card-value">{{ formattedValue }}</div>
    <div class="stat-card-label">{{ label }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  value?: number | string;
  label?: string;
  unit?: string;
}>();

const formattedValue = computed(() => {
  if (props.value === null || props.value === undefined) return '-';
  const v = typeof props.value === 'number'
    ? (Number.isInteger(props.value) ? props.value : props.value.toFixed(2))
    : props.value;
  return props.unit ? `${v} ${props.unit}` : String(v);
});
</script>
