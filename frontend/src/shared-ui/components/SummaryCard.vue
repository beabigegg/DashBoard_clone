<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  label: {
    type: String,
    required: true
  },
  value: {
    type: [Number, String],
    default: null
  },
  format: {
    type: String,
    default: null,
    validator: (v) => ['number', 'percent', 'duration', null].includes(v)
  },
  accent: {
    type: String,
    default: 'brand'
  },
  tooltip: {
    type: String,
    default: null
  },
  clickable: {
    type: Boolean,
    default: false
  },
  active: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['click'])

const ACCENT_MAP = {
  brand:   { bar: '#0080C8', text: '#0080C8' },
  success: { bar: '#22c55e', text: '#15803d' },
  warning: { bar: '#f59e0b', text: '#b45309' },
  danger:  { bar: '#ef4444', text: '#b91c1c' },
  info:    { bar: '#3b82f6', text: '#1d4ed8' },
  neutral: { bar: '#9ca3af', text: '#64748b' },
  // Equipment state tokens
  prd:     { bar: '#22c55e', text: '#15803d' },
  sby:     { bar: '#3b82f6', text: '#1d4ed8' },
  udt:     { bar: '#f59e0b', text: '#b45309' },
  sdt:     { bar: '#ef4444', text: '#b91c1c' },
  egt:     { bar: '#8b5cf6', text: '#6d28d9' },
  nst:     { bar: '#9ca3af', text: '#64748b' }
}

const accentColor = computed(() => ACCENT_MAP[props.accent] ?? ACCENT_MAP.brand)

const formattedValue = computed(() => {
  const v = props.value
  if (v === null || v === undefined) return '—'
  if (props.format === 'number') {
    const n = Number(v)
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}KK`
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
    return n.toLocaleString('zh-TW')
  }
  if (props.format === 'percent') {
    return `${Number(v).toFixed(1)}%`
  }
  if (props.format === 'duration') {
    return `${Number(v).toFixed(1)}`
  }
  return String(v)
})

// Value update animation
const valuePulse = ref(false)
watch(() => props.value, () => {
  valuePulse.value = true
  setTimeout(() => { valuePulse.value = false }, 500)
})

function handleClick() {
  if (props.clickable) emit('click')
}
</script>

<template>
  <div
    class="summary-card"
    :class="{
      'summary-card--clickable': clickable,
      'summary-card--active': clickable && active,
    }"
    :style="{ '--accent-bar': accentColor.bar, '--accent-text': accentColor.text }"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    :title="tooltip || undefined"
    @click="handleClick"
    @keydown.enter="handleClick"
    @keydown.space.prevent="handleClick"
  >
    <div class="summary-card__accent-bar" />
    <div class="summary-card__body">
      <div class="summary-card__label" :title="label">
        {{ label }}
        <span v-if="tooltip" class="summary-card__tooltip-icon" :aria-label="tooltip">?</span>
      </div>
      <div
        class="summary-card__value"
        :class="{ 'summary-card__value--pulse': valuePulse }"
      >
        {{ formattedValue }}
      </div>
      <div v-if="$slots.sub" class="summary-card__sub">
        <slot name="sub" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.summary-card {
  position: relative;
  background: theme('colors.surface.card');
  border-radius: theme('borderRadius.card');
  box-shadow: theme('boxShadow.sm');
  overflow: hidden;
  padding: 14px 16px 12px;
  border: 1px solid theme('colors.stroke.soft');
  transition:
    transform var(--motion-normal) var(--motion-ease),
    box-shadow var(--motion-normal) var(--motion-ease),
    opacity var(--motion-normal) var(--motion-ease),
    border-color var(--motion-normal) var(--motion-ease);
}

.summary-card__accent-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--accent-bar);
}

.summary-card__body {
  padding-top: 4px;
}

.summary-card__label {
  font-size: 12px;
  font-weight: 700;
  color: theme('colors.text.muted');
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.summary-card__value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--accent-text);
  font-variant-numeric: tabular-nums;
}

.summary-card__sub {
  margin-top: 6px;
  font-size: 12px;
  color: theme('colors.text.muted');
}

.summary-card__tooltip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 1px solid theme('colors.text.muted');
  font-size: 9px;
  font-weight: 700;
  color: theme('colors.text.muted');
  cursor: help;
  margin-left: 3px;
  vertical-align: middle;
  line-height: 1;
}

/* Clickable state */
.summary-card--clickable {
  cursor: pointer;
}

.summary-card--clickable:hover {
  transform: translateY(-3px);
  box-shadow: theme('boxShadow.md');
}

/* Active state */
.summary-card--active {
  border-color: theme('colors.brand.500');
  box-shadow: 0 0 0 2px rgba(0, 128, 200, 0.3), theme('boxShadow.sm');
  transform: scale(1.02);
}

/* Pulse animation */
@keyframes value-pulse {
  0%   { transform: scale(1); }
  40%  { transform: scale(1.06); }
  100% { transform: scale(1); }
}

.summary-card__value--pulse {
  animation: value-pulse 500ms var(--motion-ease);
}

@media (prefers-reduced-motion: reduce) {
  .summary-card__value--pulse {
    animation: none;
  }
  .summary-card--clickable:hover {
    transform: none;
  }
  .summary-card--active {
    transform: none;
  }
}
</style>
