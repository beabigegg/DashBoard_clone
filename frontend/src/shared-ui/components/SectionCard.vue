<script setup>
import { ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

const props = defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'elevated', 'outlined'].includes(v)
  },
  collapsible: {
    type: Boolean,
    default: false
  },
  defaultOpen: {
    type: Boolean,
    default: true
  }
})

const isOpen = ref(props.defaultOpen)

function toggle() {
  if (props.collapsible) isOpen.value = !isOpen.value
}
</script>

<template>
  <section
    class="shared-section-card"
    :class="[`shared-section-card--${variant}`]"
  >
    <header
      v-if="$slots.header"
      class="shared-section-card-header"
      :class="{ 'shared-section-card-header--collapsible': collapsible }"
      @click="toggle"
    >
      <slot name="header" />
      <ChevronDown
        v-if="collapsible"
        class="shared-section-card-chevron"
        :class="{ 'shared-section-card-chevron--open': isOpen }"
        :size="18"
      />
    </header>

    <div
      class="shared-section-card-body"
      :class="{ 'shared-section-card-body--collapsed': collapsible && !isOpen }"
    >
      <slot />
    </div>

    <footer v-if="$slots.footer && (!collapsible || isOpen)" class="shared-section-card-footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.shared-section-card {
  border: 1px solid theme('colors.stroke.soft');
  border-radius: theme('borderRadius.shell');
  background: theme('colors.surface.card');
  overflow: hidden;
}

/* variant: elevated */
.shared-section-card--elevated {
  border: none;
  box-shadow: theme('boxShadow.md');
}

/* variant: outlined */
.shared-section-card--outlined {
  background: transparent;
  border-color: theme('colors.stroke.panel');
}

.shared-section-card-header {
  padding: theme('spacing.block') theme('spacing.4');
  border-bottom: 1px solid theme('colors.stroke.soft');
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.shared-section-card-header--collapsible {
  cursor: pointer;
  user-select: none;
}

.shared-section-card-header--collapsible:hover {
  background: theme('colors.surface.hover');
}

.shared-section-card-chevron {
  color: theme('colors.text.secondary');
  transition: transform var(--motion-normal) var(--motion-ease);
  flex-shrink: 0;
}

.shared-section-card-chevron--open {
  transform: rotate(180deg);
}

.shared-section-card-body {
  padding: theme('spacing.4');
  overflow: hidden;
  max-height: 9999px;
  transition: max-height var(--motion-slow) var(--motion-ease);
}

.shared-section-card-body--collapsed {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.shared-section-card-footer {
  padding: theme('spacing.block') theme('spacing.4');
  border-top: 1px solid theme('colors.stroke.soft');
}
</style>
