<script setup lang="ts">
import LoadingSpinner from './LoadingSpinner.vue';

interface Props {
  tier?: 'page' | 'section';
}

withDefaults(defineProps<Props>(), {
  tier: 'section',
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
  z-index: 1000;
  background: rgba(15, 23, 42, 0.28);
}
</style>
