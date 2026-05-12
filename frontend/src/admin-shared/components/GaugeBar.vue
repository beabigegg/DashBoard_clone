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

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  label?: string;
  value?: number;
  max?: number;
  unit?: string;
  displayText?: string;
  warningThreshold?: number;
  dangerThreshold?: number;
}>();

const label = computed(() => props.label ?? '');
const value = computed(() => props.value ?? 0);
const max = computed(() => props.max ?? 100);
const unit = computed(() => props.unit ?? '%');
const displayText = computed(() => props.displayText ?? '');
const warningThreshold = computed(() => props.warningThreshold ?? 0.7);
const dangerThreshold = computed(() => props.dangerThreshold ?? 0.9);

const ratio = computed(() => {
  if (max.value <= 0) return 0;
  return Math.min(Math.max(value.value / max.value, 0), 1);
});

const displayValue = computed(() => {
  if (displayText.value) return displayText.value;
  if (unit.value === '%') {
    return `${(ratio.value * 100).toFixed(1)}%`;
  }
  return `${value.value}${unit.value ? ' ' + unit.value : ''}`;
});

const fillColor = computed(() => {
  if (ratio.value >= dangerThreshold.value) return 'var(--color-token-hef4444)';
  if (ratio.value >= warningThreshold.value) return 'var(--color-token-hf59e0b)';
  return 'var(--color-token-h22c55e)';
});

const fillStyle = computed(() => ({
  width: `${ratio.value * 100}%`,
  backgroundColor: fillColor.value,
}));
</script>
