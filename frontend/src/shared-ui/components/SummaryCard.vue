<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Props {
  label: string;
  value?: number | string | null;
  format?: 'number' | 'percent' | 'duration' | null;
  accent?: string;
  tooltip?: string | null;
  clickable?: boolean;
  active?: boolean;
  warningThreshold?: number;
  dangerThreshold?: number;
  thresholdValue?: number;
}

const props = withDefaults(defineProps<Props>(), {
  value: null,
  format: null,
  accent: 'brand',
  tooltip: null,
  clickable: false,
  active: false,
});

const emit = defineEmits<{
  (e: 'click'): void;
}>();

const accentColor = computed(() => {
  const cmp = props.thresholdValue ?? props.value
  const n = Number(cmp)
  if (!Number.isFinite(n)) return props.accent ?? 'brand'
  if (props.dangerThreshold != null && n >= props.dangerThreshold) return 'danger'
  if (props.warningThreshold != null && n >= props.warningThreshold) return 'warning'
  return props.accent ?? 'brand'
})

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
    :data-accent="accentColor"
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

/* Accent tokens — all colors resolved via theme() to avoid hardcoded HEX */
.summary-card[data-accent="brand"]   { --accent-bar: theme('colors.brand.500');    --accent-text: theme('colors.brand.500'); }
.summary-card[data-accent="success"] { --accent-bar: theme('colors.state.success'); --accent-text: theme('colors.token.h15803d'); }
.summary-card[data-accent="warning"] { --accent-bar: theme('colors.state.warning'); --accent-text: theme('colors.token.hb45309'); }
.summary-card[data-accent="danger"]  { --accent-bar: theme('colors.state.danger');  --accent-text: theme('colors.token.hb91c1c'); }
.summary-card[data-accent="info"]    { --accent-bar: theme('colors.state.info');    --accent-text: theme('colors.token.h1d4ed8'); }
.summary-card[data-accent="neutral"] { --accent-bar: theme('colors.state.neutral'); --accent-text: theme('colors.text.secondary'); }
.summary-card[data-accent="prd"]     { --accent-bar: theme('colors.state.success'); --accent-text: theme('colors.token.h15803d'); }
.summary-card[data-accent="sby"]     { --accent-bar: theme('colors.state.info');    --accent-text: theme('colors.token.h1d4ed8'); }
.summary-card[data-accent="udt"]     { --accent-bar: theme('colors.state.danger');  --accent-text: theme('colors.token.hb91c1c'); }
.summary-card[data-accent="sdt"]     { --accent-bar: theme('colors.state.warning'); --accent-text: theme('colors.token.hb45309'); }
.summary-card[data-accent="egt"]     { --accent-bar: theme('colors.state.info');    --accent-text: theme('colors.token.h1d4ed8'); }
.summary-card[data-accent="nst"]     { --accent-bar: theme('colors.state.neutral'); --accent-text: theme('colors.text.secondary'); }
</style>
