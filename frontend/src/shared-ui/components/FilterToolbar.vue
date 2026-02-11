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
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.shared-filter-toolbar-main,
.shared-filter-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
