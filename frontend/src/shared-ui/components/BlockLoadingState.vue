<script setup lang="ts">
import LoadingSpinner from './LoadingSpinner.vue';

interface Props {
  text?: string;
  minHeight?: string;
}

withDefaults(defineProps<Props>(), {
  text: '載入中...',
  minHeight: '120px',
});
</script>

<template>
  <div class="block-loading-state" :style="{ minHeight }">
    <LoadingSpinner size="md" />
    <span class="block-loading-state__text">{{ text }}</span>
  </div>
</template>

<style scoped>
.block-loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: theme('colors.text.secondary');
  font-size: 13px;
}

.block-loading-state__text {
  color: inherit;
}
</style>
