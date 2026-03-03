<script setup>
import { computed } from 'vue';
import MultiSelect from '../../resource-shared/components/MultiSelect.vue';

const props = defineProps({
  holdType: {
    type: String,
    default: 'all',
  },
  reason: {
    type: Array,
    default: () => [],
  },
  reasons: {
    type: Array,
    default: () => [],
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['change']);

const HOLD_TYPE_OPTIONS = Object.freeze([
  { value: 'quality', label: '品質異常' },
  { value: 'non-quality', label: '非品質異常' },
  { value: 'all', label: '全部' },
]);

const holdTypeModel = computed(() => props.holdType || 'all');

const reasonOptions = computed(() => {
  const unique = new Set();
  const items = [];
  (props.reasons || []).forEach((reason) => {
    const value = String(reason || '').trim();
    if (!value || unique.has(value)) {
      return;
    }
    unique.add(value);
    items.push(value);
  });
  return items;
});

function selectHoldType(nextValue) {
  if (props.disabled) {
    return;
  }
  const normalized = nextValue || 'all';
  if (normalized === holdTypeModel.value) {
    return;
  }
  emit('change', {
    holdType: normalized,
    reason: props.reason || [],
  });
}

function onReasonChange(nextValues) {
  emit('change', {
    holdType: props.holdType || 'all',
    reason: nextValues || [],
  });
}
</script>

<template>
  <section class="filter-bar card hold-overview-filter-bar">
    <div class="filter-group hold-type-group hold-overview-hold-type-group">
      <span class="filter-label">Hold Type</span>
      <div class="hold-type-segment" role="radiogroup" aria-label="Hold Type">
        <button
          v-for="item in HOLD_TYPE_OPTIONS"
          :key="item.value"
          type="button"
          role="radio"
          class="hold-type-btn"
          :class="{ active: holdTypeModel === item.value }"
          :aria-checked="holdTypeModel === item.value"
          :disabled="disabled"
          @click="selectHoldType(item.value)"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <div class="filter-group reason-group hold-overview-reason-group">
      <span class="filter-label">Reason</span>
      <MultiSelect
        :model-value="reason"
        :options="reasonOptions"
        :disabled="disabled"
        :searchable="true"
        placeholder="全部"
        @update:model-value="onReasonChange"
      />
    </div>
  </section>
</template>
