<script setup>
import { computed, ref } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import Chip from './Chip.vue'

const props = defineProps({
  activeFilters: {
    type: Array,
    default: null
    // Expected shape: [{ key, label, tone? }]
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

const emit = defineEmits(['remove-filter'])

const isOpen = ref(props.defaultOpen)

const hasActiveFilters = computed(
  () => Array.isArray(props.activeFilters) && props.activeFilters.length > 0
)

function toggle() {
  isOpen.value = !isOpen.value
}
</script>

<template>
  <section class="shared-filter-toolbar" role="region" aria-label="filters">
    <!-- Active filter chips row -->
    <div v-if="hasActiveFilters" class="shared-filter-chips">
      <Chip
        v-for="filter in activeFilters"
        :key="filter.key"
        :label="filter.label"
        :tone="filter.tone || 'brand'"
        removable
        @remove="emit('remove-filter', filter.key)"
      />
    </div>

    <!-- Main filter area: always visible OR collapsed behind expand toggle -->
    <template v-if="!collapsible || isOpen">
      <div class="shared-filter-toolbar-main">
        <slot />
      </div>
      <div v-if="$slots.actions" class="shared-filter-toolbar-actions">
        <slot name="actions" />
      </div>
    </template>

    <!-- Collapsible toggle -->
    <button
      v-if="collapsible"
      type="button"
      class="shared-filter-expand-btn"
      :aria-expanded="isOpen"
      @click="toggle"
    >
      <ChevronDown
        class="shared-filter-chevron"
        :class="{ 'shared-filter-chevron--open': isOpen }"
        :size="16"
      />
      {{ isOpen ? '收起篩選' : '展開篩選' }}
    </button>
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

.shared-filter-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  width: 100%;
}

.shared-filter-toolbar-main,
.shared-filter-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: theme('spacing.2');
  align-items: center;
}

.shared-filter-expand-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: theme('colors.text.secondary');
  padding: 2px 4px;
  border-radius: 4px;
}

.shared-filter-expand-btn:hover {
  background: theme('colors.surface.hover');
  color: theme('colors.text.primary');
}

.shared-filter-chevron {
  transition: transform var(--motion-fast) var(--motion-ease);
}

.shared-filter-chevron--open {
  transform: rotate(180deg);
}
</style>
