<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  label: string;
  tone?: 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info';
  removable?: boolean;
  clickable?: boolean;
  disabled?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  tone: 'neutral',
  removable: false,
  clickable: false,
  disabled: false,
});

const emit = defineEmits<{
  (e: 'remove'): void;
  (e: 'click'): void;
}>();

const TONE_CLASSES: Record<string, string> = {
  neutral: 'chip--neutral',
  brand:   'chip--brand',
  success: 'chip--success',
  warning: 'chip--warning',
  danger:  'chip--danger',
  info:    'chip--info',
}

const toneClass = computed(() => TONE_CLASSES[props.tone] ?? 'chip--neutral')

function handleClick() {
  if (!props.disabled && props.clickable) emit('click')
}

function handleRemove(e: MouseEvent) {
  e.stopPropagation()
  if (!props.disabled) emit('remove')
}
</script>

<template>
  <span
    class="chip"
    :class="[
      toneClass,
      {
        'chip--clickable': clickable,
        'chip--disabled': disabled,
      }
    ]"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable && !disabled ? 0 : undefined"
    :aria-disabled="disabled || undefined"
    @click="handleClick"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    {{ label }}
    <button
      v-if="removable"
      type="button"
      class="chip__remove"
      :disabled="disabled"
      :aria-label="`移除 ${label}`"
      @click="handleRemove"
    >
      <X :size="12" />
    </button>
  </span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: theme('borderRadius.pill');
  font-size: 12px;
  font-weight: 500;
  line-height: 1.6;
  white-space: nowrap;
  border: 1px solid transparent;
  transition: opacity var(--motion-fast) var(--motion-ease);
}

.chip--neutral {
  background: theme('colors.surface.muted');
  color: theme('colors.text.subtle');
  border-color: theme('colors.stroke.soft');
}

.chip--brand {
  background: theme('colors.brand.50');
  color: theme('colors.brand.700');
  border-color: theme('colors.brand.100');
}

.chip--success {
  background: theme('colors.token.hdcfce7');
  color: theme('colors.token.h15803d');
  border-color: theme('colors.token.hbbf7d0');
}

.chip--warning {
  background: theme('colors.token.hfef3c7');
  color: theme('colors.token.hb45309');
  border-color: theme('colors.token.hfde68a');
}

.chip--danger {
  background: theme('colors.token.hfee2e2');
  color: theme('colors.token.hb91c1c');
  border-color: theme('colors.token.hfecaca');
}

.chip--info {
  background: theme('colors.token.hdbeafe');
  color: theme('colors.token.h1d4ed8');
  border-color: theme('colors.token.hbfdbfe');
}

.chip--clickable {
  cursor: pointer;
}

.chip--clickable:hover:not(.chip--disabled) {
  filter: brightness(0.95);
}

.chip--disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chip__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  margin-left: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: inherit;
  opacity: 0.7;
  line-height: 1;
}

.chip__remove:hover:not(:disabled) {
  opacity: 1;
}

.chip__remove:disabled {
  cursor: not-allowed;
}
</style>
