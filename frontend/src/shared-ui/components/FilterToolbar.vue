<template>
  <section class="shared-filter-toolbar" role="region" aria-label="filters">
    <div class="shared-filter-toolbar-main">
      <slot />
    </div>
    <div v-if="$slots.actions" class="shared-filter-toolbar-actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<style scoped>
.shared-filter-toolbar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: theme('spacing.block');
  padding: theme('spacing.block');
  border-radius: theme('borderRadius.card');
  border: 1px solid theme('colors.stroke.soft');
  background: theme('colors.surface.muted');
}

.shared-filter-toolbar-main,
.shared-filter-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: theme('spacing.2');
  align-items: center;
}
</style>
