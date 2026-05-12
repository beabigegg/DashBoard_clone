<template>
  <div class="status-dot-wrapper">
    <span class="status-dot" :class="'status-dot--' + status"></span>
    <span class="status-dot-label">{{ label }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  status?: 'healthy' | 'degraded' | 'error' | 'disabled';
  label?: string;
}>();
</script>
