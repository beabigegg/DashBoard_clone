<script setup lang="ts">
interface Props {
  size?: 'sm' | 'md' | 'lg';
}

withDefaults(defineProps<Props>(), {
  size: 'md',
});

const sizeMap: Record<string, { diameter: string; border: string }> = {
  sm: { diameter: '14px', border: '2px' },
  md: { diameter: '24px', border: '3px' },
  lg: { diameter: '42px', border: '4px' },
};
</script>

<template>
  <span
    class="loading-spinner"
    :style="{
      width: sizeMap[size].diameter,
      height: sizeMap[size].diameter,
      borderWidth: sizeMap[size].border,
    }"
    aria-label="載入中"
    role="status"
  />
</template>

<style scoped>
.loading-spinner {
  display: inline-block;
  border-style: solid;
  border-color: currentColor transparent transparent transparent;
  border-radius: 50%;
  animation: spinner-spin 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes spinner-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .loading-spinner {
    animation: none;
    border-top-color: currentColor;
    opacity: 0.5;
  }
}
</style>
