<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useTransition, TransitionPresets } from '@vueuse/core'

interface Props {
  label: string;
  value?: number | string | null;
  format?: 'number' | 'percent' | 'duration' | null;
  precision?: number | null;
  accent?: string;
  tooltip?: string | null;
  clickable?: boolean;
  active?: boolean;
  warningThreshold?: number;
  dangerThreshold?: number;
  thresholdValue?: number;
  subValue?: number | null;
  subUnit?: string;
}

const props = withDefaults(defineProps<Props>(), {
  value: null,
  format: null,
  precision: null,
  accent: 'brand',
  tooltip: null,
  clickable: false,
  active: false,
  subValue: null,
  subUnit: '',
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

// ── Count-up animation for main value ────────────────────────────────────

const mainSource = ref(0)
watch(
  () => {
    const v = props.value
    if (v === null || v === undefined) return 0
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  },
  (val) => { mainSource.value = val },
  { immediate: true },
)
const animatedMain = useTransition(mainSource, {
  duration: 900,
  transition: TransitionPresets.easeOutExpo,
})

const formattedValue = computed(() => {
  const v = props.value
  if (v === null || v === undefined) return '—'
  if (!props.format) return String(v)

  const n = animatedMain.value
  const dec = props.precision ?? 1
  if (props.format === 'number') {
    const abs = Math.abs(n)
    const sign = n < 0 ? '-' : ''
    if (abs >= 1e6) return dec === 0 ? `${sign}${Math.round(abs / 1e6)}KK` : `${sign}${(abs / 1e6).toFixed(dec)}KK`
    if (abs >= 1e3) return dec === 0 ? `${sign}${Math.round(abs / 1e3)}K` : `${sign}${(abs / 1e3).toFixed(dec)}K`
    if (props.precision != null) return n.toFixed(props.precision)
    return Math.round(n).toLocaleString('zh-TW')
  }
  if (props.format === 'percent') return `${n.toFixed(dec)}%`
  if (props.format === 'duration') return `${n.toFixed(dec)}`
  return String(v)
})

// ── Count-up animation for sub raw value ────────────────────────────────

const subSource = ref(0)
watch(
  () => (props.subValue !== null && props.subValue !== undefined ? Number(props.subValue) || 0 : 0),
  (val) => { subSource.value = val },
  { immediate: true },
)
const animatedSub = useTransition(subSource, {
  duration: 900,
  transition: TransitionPresets.easeOutExpo,
})

const formattedSubValue = computed(() => {
  if (props.subValue === null || props.subValue === undefined) return null
  const n = Math.round(animatedSub.value)
  return n.toLocaleString('zh-TW') + (props.subUnit || '')
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
      <div class="summary-card__value">
        {{ formattedValue }}
      </div>
      <div v-if="formattedSubValue !== null" class="summary-card__sub-num">
        {{ formattedSubValue }}
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

.summary-card__sub-num {
  margin-top: 5px;
  font-size: 11px;
  font-weight: 500;
  color: theme('colors.text.muted');
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.01em;
}

.summary-card__sub {
  margin-top: 6px;
  font-size: 12px;
  color: theme('colors.text.muted');
}

/* Radial ambient glow behind content (revealed on hover) */
.summary-card::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
  background: radial-gradient(
    circle at 30% 60%,
    var(--summary-glow-bg, rgba(0, 128, 200, 0.05)) 0%,
    transparent 65%
  );
  opacity: 0;
  transition: opacity 0.25s ease;
}

/* Universal hover — all cards lift + glow */
.summary-card:hover {
  transform: translateY(-2px);
  box-shadow:
    0 0 0 1px var(--summary-glow-ring, rgba(0, 128, 200, 0.2)),
    0 0 20px var(--summary-glow-halo, rgba(0, 128, 200, 0.2)),
    0 4px 12px rgba(0, 0, 0, 0.08);
}

.summary-card:hover::after {
  opacity: 1;
}

/* Clickable state */
.summary-card--clickable {
  cursor: pointer;
}

.summary-card--clickable:hover {
  transform: translateY(-3px);
}

/* Active state */
.summary-card--active {
  border-color: theme('colors.brand.500');
  box-shadow: 0 0 0 2px rgba(0, 128, 200, 0.3), theme('boxShadow.sm');
  transform: scale(1.02);
}

@media (prefers-reduced-motion: reduce) {
  .summary-card:hover,
  .summary-card--clickable:hover {
    transform: none;
  }
  .summary-card--active {
    transform: none;
  }
}

/* Accent tokens */
.summary-card[data-accent="brand"]   { --accent-bar: theme('colors.brand.500');    --accent-text: theme('colors.brand.500');          --summary-glow-bg: rgba(0, 128, 200, 0.05);   --summary-glow-ring: rgba(0, 128, 200, 0.2);   --summary-glow-halo: rgba(0, 128, 200, 0.2); }
.summary-card[data-accent="success"] { --accent-bar: theme('colors.state.success'); --accent-text: theme('colors.token.h15803d');     --summary-glow-bg: rgba(34, 197, 94, 0.05);   --summary-glow-ring: rgba(34, 197, 94, 0.2);   --summary-glow-halo: rgba(34, 197, 94, 0.2); }
.summary-card[data-accent="warning"] { --accent-bar: theme('colors.state.warning'); --accent-text: theme('colors.token.hb45309');     --summary-glow-bg: rgba(245, 158, 11, 0.05);  --summary-glow-ring: rgba(245, 158, 11, 0.2);  --summary-glow-halo: rgba(245, 158, 11, 0.2); }
.summary-card[data-accent="danger"]  { --accent-bar: theme('colors.state.danger');  --accent-text: theme('colors.token.hb91c1c');     --summary-glow-bg: rgba(239, 68, 68, 0.05);   --summary-glow-ring: rgba(239, 68, 68, 0.2);   --summary-glow-halo: rgba(239, 68, 68, 0.2); }
.summary-card[data-accent="info"]    { --accent-bar: theme('colors.state.info');    --accent-text: theme('colors.token.h1d4ed8');     --summary-glow-bg: rgba(59, 130, 246, 0.05);  --summary-glow-ring: rgba(59, 130, 246, 0.2);  --summary-glow-halo: rgba(59, 130, 246, 0.2); }
.summary-card[data-accent="neutral"] { --accent-bar: theme('colors.state.neutral'); --accent-text: theme('colors.text.secondary');    --summary-glow-bg: rgba(107, 114, 128, 0.05); --summary-glow-ring: rgba(107, 114, 128, 0.2); --summary-glow-halo: rgba(107, 114, 128, 0.2); }
.summary-card[data-accent="prd"]     { --accent-bar: theme('colors.state.success'); --accent-text: theme('colors.token.h15803d');     --summary-glow-bg: rgba(34, 197, 94, 0.05);   --summary-glow-ring: rgba(34, 197, 94, 0.2);   --summary-glow-halo: rgba(34, 197, 94, 0.2); }
.summary-card[data-accent="sby"]     { --accent-bar: theme('colors.state.info');    --accent-text: theme('colors.token.h1d4ed8');     --summary-glow-bg: rgba(59, 130, 246, 0.05);  --summary-glow-ring: rgba(59, 130, 246, 0.2);  --summary-glow-halo: rgba(59, 130, 246, 0.2); }
.summary-card[data-accent="udt"]     { --accent-bar: theme('colors.state.danger');  --accent-text: theme('colors.token.hb91c1c');     --summary-glow-bg: rgba(239, 68, 68, 0.05);   --summary-glow-ring: rgba(239, 68, 68, 0.2);   --summary-glow-halo: rgba(239, 68, 68, 0.2); }
.summary-card[data-accent="sdt"]     { --accent-bar: theme('colors.state.warning'); --accent-text: theme('colors.token.hb45309');     --summary-glow-bg: rgba(245, 158, 11, 0.05);  --summary-glow-ring: rgba(245, 158, 11, 0.2);  --summary-glow-halo: rgba(245, 158, 11, 0.2); }
.summary-card[data-accent="egt"]     { --accent-bar: theme('colors.state.info');    --accent-text: theme('colors.token.h1d4ed8');     --summary-glow-bg: rgba(59, 130, 246, 0.05);  --summary-glow-ring: rgba(59, 130, 246, 0.2);  --summary-glow-halo: rgba(59, 130, 246, 0.2); }
.summary-card[data-accent="nst"]     { --accent-bar: theme('colors.state.neutral'); --accent-text: theme('colors.text.secondary');    --summary-glow-bg: rgba(107, 114, 128, 0.05); --summary-glow-ring: rgba(107, 114, 128, 0.2); --summary-glow-halo: rgba(107, 114, 128, 0.2); }

@media (prefers-reduced-motion: reduce) {
  .summary-card::after { transition: none; }
}
</style>
