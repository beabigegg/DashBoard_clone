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
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}

.shared-section-card-header,
.shared-section-card-footer {
  padding: 12px 16px;
}

.shared-section-card-body {
  padding: 16px;
}

.shared-section-card-header {
  border-bottom: 1px solid #e2e8f0;
}

.shared-section-card-footer {
  border-top: 1px solid #e2e8f0;
}
</style>
