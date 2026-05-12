<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  type?: string;
  rows?: number;
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  rows: 3,
});

const normalizedType = computed(() => {
  if (props.type === 'card' || props.type === 'table') {
    return props.type;
  }
  return 'text';
});

const normalizedRows = computed(() => {
  const parsed = Number(props.rows);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 1;
  }
  return Math.floor(parsed);
});

const rowIndexes = computed(() =>
  Array.from({ length: normalizedRows.value }, (_, index) => index),
);
</script>

<template>
  <div class="skeleton-loader" :class="`skeleton-loader--${normalizedType}`" aria-hidden="true">
    <template v-if="normalizedType === 'text'">
      <div
        v-for="index in rowIndexes"
        :key="`text-${index}`"
        class="skeleton-shimmer skeleton-line"
        :style="{ width: index === rowIndexes.length - 1 ? '72%' : '100%' }"
      />
    </template>

    <template v-else-if="normalizedType === 'card'">
      <div
        v-for="index in rowIndexes"
        :key="`card-${index}`"
        class="skeleton-card"
      >
        <div class="skeleton-shimmer skeleton-line skeleton-line--title" />
        <div class="skeleton-shimmer skeleton-line" />
        <div class="skeleton-shimmer skeleton-line skeleton-line--short" />
      </div>
    </template>

    <template v-else>
      <div class="skeleton-table">
        <div class="skeleton-table-row skeleton-table-row--head">
          <div v-for="column in 5" :key="`head-${column}`" class="skeleton-shimmer skeleton-cell" />
        </div>
        <div
          v-for="index in rowIndexes"
          :key="`table-${index}`"
          class="skeleton-table-row"
        >
          <div v-for="column in 5" :key="`cell-${index}-${column}`" class="skeleton-shimmer skeleton-cell" />
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.skeleton-loader {
  display: grid;
  gap: 10px;
}

.skeleton-shimmer {
  position: relative;
  overflow: hidden;
  background: theme('colors.stroke.soft');
}

.skeleton-shimmer::after {
  content: '';
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.65), transparent);
  animation: skeleton-shimmer 1.25s ease-in-out infinite;
}

.skeleton-line {
  height: 12px;
  border-radius: 999px;
}

.skeleton-line--title {
  width: 45%;
}

.skeleton-line--short {
  width: 62%;
}

.skeleton-card {
  display: grid;
  gap: 10px;
  padding: theme('spacing.token.p14');
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 10px;
  background: theme('colors.surface.muted');
}

.skeleton-table {
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 10px;
  overflow: hidden;
}

.skeleton-table-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.skeleton-table-row + .skeleton-table-row {
  border-top: 1px solid theme('colors.stroke.soft');
}

.skeleton-table-row--head {
  background: theme('colors.brand.50');
}

.skeleton-cell {
  height: 14px;
  margin: theme('spacing.token.p10');
  border-radius: 999px;
}

@keyframes skeleton-shimmer {
  100% {
    transform: translateX(100%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton-shimmer::after {
    animation: none;
  }
}
</style>
