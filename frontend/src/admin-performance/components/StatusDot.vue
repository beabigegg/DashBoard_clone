<template>
  <div class="status-dot-wrapper">
    <span class="status-dot" :class="'status-dot--' + status"></span>
    <span class="status-dot-label">{{ label }}</span>
  </div>
</template>

<script setup>
defineProps({
  status: {
    type: String,
    default: 'disabled',
    validator: (v) => ['healthy', 'degraded', 'error', 'disabled'].includes(v),
  },
  label: { type: String, default: '' },
});
</script>
