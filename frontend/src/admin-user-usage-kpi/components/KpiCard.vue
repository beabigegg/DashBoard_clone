<script setup>
defineProps({
  value: { type: [Number, String], default: '-' },
  label: { type: String, default: '' },
  suffix: { type: String, default: '' },
});
</script>

<template>
  <div class="kpi-card">
    <div class="kpi-card-value">{{ value ?? '-' }}{{ suffix }}</div>
    <div class="kpi-card-label">{{ label }}</div>
  </div>
</template>
