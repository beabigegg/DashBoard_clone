<script setup>
import LoadingSpinner from './LoadingSpinner.vue';

defineProps({
  tier: {
    type: String,
    default: 'section',
    validator: (v) => ['page', 'section'].includes(v),
  },
});
</script>

<template>
  <div class="loading-overlay" :class="`loading-overlay--${tier}`">
    <LoadingSpinner :size="tier === 'page' ? 'lg' : 'md'" />
  </div>
</template>

<style scoped>
.loading-overlay {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--overlay-bg);
  z-index: 10;
}

.loading-overlay--section {
  position: absolute;
  inset: 0;
}

.loading-overlay--page {
  position: fixed;
  inset: 0;
  z-index: 100;
}
</style>
