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
      <label class="filter-label" for="hold-history-hold-type">Hold Type</label>
      <select
        id="hold-history-hold-type"
        v-model="holdTypeModel"
        class="hold-type-select"
        :disabled="disabled"
      >
        <option value="quality">品質異常</option>
        <option value="non-quality">非品質異常</option>
        <option value="all">全部</option>
      </select>
    </div>
  </section>
</template>
