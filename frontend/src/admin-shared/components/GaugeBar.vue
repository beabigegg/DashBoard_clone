<template>
  <div class="gauge-bar">
    <div class="gauge-bar-header">
      <span class="gauge-bar-label">{{ label }}</span>
      <span class="gauge-bar-value">{{ displayValue }}</span>
    </div>
    <div class="gauge-bar-track">
      <div class="gauge-bar-fill" :style="fillStyle"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  label: { type: String, default: '' },
  value: { type: Number, default: 0 },
  max: { type: Number, default: 100 },
  unit: { type: String, default: '%' },
  displayText: { type: String, default: '' },
  warningThreshold: { type: Number, default: 0.7 },
  dangerThreshold: { type: Number, default: 0.9 },
});

const ratio = computed(() => {
  if (props.max <= 0) return 0;
  return Math.min(Math.max(props.value / props.max, 0), 1);
});

const displayValue = computed(() => {
  if (props.displayText) return props.displayText;
  if (props.unit === '%') {
    return `${(ratio.value * 100).toFixed(1)}%`;
  }
  return `${props.value}${props.unit ? ' ' + props.unit : ''}`;
});

const fillColor = computed(() => {
  if (ratio.value >= props.dangerThreshold) return 'var(--color-token-hef4444)';
  if (ratio.value >= props.warningThreshold) return 'var(--color-token-hf59e0b)';
  return 'var(--color-token-h22c55e)';
});

const fillStyle = computed(() => ({
  width: `${ratio.value * 100}%`,
  backgroundColor: fillColor.value,
}));
</script>
