<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  columns?: number | string;
}

const props = withDefaults(defineProps<Props>(), {
  columns: 'auto',
});

const gridStyle = computed(() => {
  if (!props.columns || props.columns === 'auto') {
    return { gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))' }
  }
  return { gridTemplateColumns: `repeat(${props.columns}, minmax(0, 1fr))` }
})
</script>

<template>
  <div class="summary-card-group" :style="gridStyle">
    <slot />
  </div>
</template>

<style scoped>
.summary-card-group {
  display: grid;
  gap: 10px;
}

@media (max-width: 1000px) {
  .summary-card-group {
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  }
}

@media (max-width: 768px) {
  .summary-card-group {
    grid-template-columns: 1fr !important;
  }
}
</style>
