<script setup>
import { computed } from 'vue';

const props = defineProps({
  holdType: {
    type: String,
    default: 'quality',
  },
  reason: {
    type: String,
    default: '',
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

const holdTypeModel = computed({
  get() {
    return props.holdType || 'quality';
  },
  set(nextValue) {
    emit('change', {
      holdType: nextValue || 'quality',
      reason: props.reason || '',
    });
  },
});

const reasonModel = computed({
  get() {
    return props.reason || '';
  },
  set(nextValue) {
    emit('change', {
      holdType: props.holdType || 'quality',
      reason: nextValue || '',
    });
  },
});

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
</script>

<template>
  <section class="filter-bar card">
    <div class="filter-group hold-type-group">
      <span class="filter-label">Hold Type</span>
      <div class="radio-group">
        <label class="radio-option" :class="{ active: holdTypeModel === 'quality' }">
          <input v-model="holdTypeModel" type="radio" value="quality" :disabled="disabled" />
          <span>品質異常</span>
        </label>
        <label class="radio-option" :class="{ active: holdTypeModel === 'non-quality' }">
          <input v-model="holdTypeModel" type="radio" value="non-quality" :disabled="disabled" />
          <span>非品質異常</span>
        </label>
        <label class="radio-option" :class="{ active: holdTypeModel === 'all' }">
          <input v-model="holdTypeModel" type="radio" value="all" :disabled="disabled" />
          <span>全部</span>
        </label>
      </div>
    </div>

    <div class="filter-group reason-group">
      <label class="filter-label" for="hold-overview-reason">Reason</label>
      <select
        id="hold-overview-reason"
        v-model="reasonModel"
        class="reason-select"
        :disabled="disabled"
      >
        <option value="">全部</option>
        <option v-for="item in reasonOptions" :key="item" :value="item">
          {{ item }}
        </option>
      </select>
    </div>
  </section>
</template>
