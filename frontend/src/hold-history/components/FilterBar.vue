<script setup>
import { computed, ref, watch } from 'vue';

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

const emit = defineEmits(['apply', 'hold-type-change']);

// Local date state — changes don't auto-trigger queries
const localStartDate = ref(props.startDate);
const localEndDate = ref(props.endDate);

// Sync from parent when props change (URL restore, programmatic set)
watch(
  () => props.startDate,
  (v) => {
    localStartDate.value = v;
  },
);
watch(
  () => props.endDate,
  (v) => {
    localEndDate.value = v;
  },
);

// Hold type still emits immediately (cache-only refresh, no Oracle query)
const holdTypeModel = computed({
  get() {
    return props.holdType || 'quality';
  },
  set(nextValue) {
    emit('hold-type-change', nextValue || 'quality');
  },
});

function handleApply() {
  emit('apply', {
    startDate: localStartDate.value,
    endDate: localEndDate.value,
  });
}
</script>

<template>
  <section class="filter-bar card">
    <div class="filter-group date-group">
      <label class="filter-label" for="hold-history-start-date">開始日期</label>
      <input
        id="hold-history-start-date"
        v-model="localStartDate"
        class="date-input"
        type="date"
        :disabled="disabled"
      />
    </div>

    <div class="filter-group date-group">
      <label class="filter-label" for="hold-history-end-date">結束日期</label>
      <input
        id="hold-history-end-date"
        v-model="localEndDate"
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

    <div class="filter-group filter-action-group">
      <button
        type="button"
        class="btn btn-primary btn-query"
        :disabled="disabled"
        @click="handleApply"
      >
        <template v-if="disabled"><span class="btn-spinner"></span>查詢中...</template>
        <template v-else>查詢</template>
      </button>
    </div>
  </section>
</template>
