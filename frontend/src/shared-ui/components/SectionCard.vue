<template>
  <section class="shared-section-card">
    <header v-if="$slots.header" class="shared-section-card-header">
      <slot name="header" />
    </header>
    <div class="shared-section-card-body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="shared-section-card-footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.shared-section-card {
  border: 1px solid theme('colors.stroke.soft');
  border-radius: theme('borderRadius.shell');
  background: theme('colors.surface.card');
}

.shared-section-card-header,
.shared-section-card-footer {
  padding: theme('spacing.block') theme('spacing.4');
}

.shared-section-card-body {
  padding: theme('spacing.4');
}

.shared-section-card-header {
  border-bottom: 1px solid theme('colors.stroke.soft');
}

.shared-section-card-footer {
  border-top: 1px solid theme('colors.stroke.soft');
}
</style>
