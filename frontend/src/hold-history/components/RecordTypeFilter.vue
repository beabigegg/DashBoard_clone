<script setup>
import { computed } from 'vue';

const props = defineProps({
  modelValue: {
    type: String,
    default: 'on_hold',
  },
  mode: {
    type: String,
    default: 'range',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update:modelValue']);

const TODAY_OPTIONS = [
  {
    value: 'on_hold',
    label: '當日ON HOLD快照',
    tooltip: '班次結束時（07:30）仍在 Hold 的 lot — hold_day ≤ 今日 且尚未釋放或班次後才釋放。Hours 凍結於 07:30。',
  },
  {
    value: 'new',
    label: '當日新增',
    tooltip: 'hold_day = 今日（07:30 前一天 → 07:30 今日進入的 Hold）。含同日已釋放者，與快照有重疊。',
  },
  {
    value: 'release',
    label: '當日 Release',
    tooltip: 'release_day = 今日。與「當日ON HOLD快照」互斥（快照定義排除今日已釋放）。',
  },
];

const CURRENT_OPTIONS = [
  {
    value: 'on_hold',
    label: 'ON HOLD',
    tooltip: '目前 RELEASETXNDATE IS NULL 的所有 lot，即時狀態。Hours 以 SYSDATE 計算。',
  },
  {
    value: 'new',
    label: '現況新增',
    tooltip: 'hold_day = 本班次起始日（07:30 今日起）。含本班次已釋放者，與 ON HOLD 有重疊。',
  },
  {
    value: 'release',
    label: '現況 Release',
    tooltip: 'release_day = 本班次起始日。與「ON HOLD」互斥（已釋放則不在 ON HOLD 中）。',
  },
];

const activeOptions = computed(() => (props.mode === 'current' ? CURRENT_OPTIONS : TODAY_OPTIONS));

function select(value) {
  if (props.disabled || value === props.modelValue) return;
  emit('update:modelValue', value);
}
</script>

<template>
  <!-- Hidden in range mode per spec -->
  <section v-if="mode === 'today' || mode === 'current'" class="record-type-filter">
    <span class="filter-label">Record Type</span>
    <div class="checkbox-group">
      <label
        v-for="opt in activeOptions"
        :key="opt.value"
        class="checkbox-option"
        :class="{ active: modelValue === opt.value, disabled }"
        :title="opt.tooltip"
        @click="select(opt.value)"
      >
        <span>{{ opt.label }}</span>
      </label>
    </div>
  </section>
</template>
