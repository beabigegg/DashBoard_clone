<script setup>
import { computed } from 'vue';

const props = defineProps({
  startDate: {
    type: String,
    default: '',
  },
  endDate: {
    type: String,
    default: '',
  },
  holdType: {
    type: String,
    default: 'quality',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['change']);

function emitChange(next) {
  emit('change', {
    startDate: next.startDate ?? props.startDate,
    endDate: next.endDate ?? props.endDate,
    holdType: next.holdType ?? props.holdType,
  });
}

const startDateModel = computed({
  get() {
    return props.startDate || '';
  },
  set(nextValue) {
    emitChange({ startDate: nextValue || '' });
  },
});

const endDateModel = computed({
  get() {
    return props.endDate || '';
  },
  set(nextValue) {
    emitChange({ endDate: nextValue || '' });
  },
});

const holdTypeModel = computed({
  get() {
    return props.holdType || 'quality';
  },
  set(nextValue) {
    emitChange({ holdType: nextValue || 'quality' });
  },
});
</script>

<template>
  <section class="filter-bar card">
    <div class="filter-group date-group">
      <label class="filter-label" for="hold-history-start-date">開始日期</label>
      <input
        id="hold-history-start-date"
        v-model="startDateModel"
        class="date-input"
        type="date"
        :disabled="disabled"
      />
    </div>

    <div class="filter-group date-group">
      <label class="filter-label" for="hold-history-end-date">結束日期</label>
      <input
        id="hold-history-end-date"
        v-model="endDateModel"
        class="date-input"
        type="date"
        :disabled="disabled"
      />
    </div>

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
  </section>
</template>
