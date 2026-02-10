<script setup>
import MultiSelect from './MultiSelect.vue';

const props = defineProps({
  filters: {
    type: Object,
    required: true,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  availableLossReasons: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['update-filters', 'query']);

function updateFilters(patch) {
  emit('update-filters', {
    ...props.filters,
    ...patch,
  });
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="filter-row">
        <div class="filter-field">
          <label for="msd-start-date">開始</label>
          <input
            id="msd-start-date"
            type="date"
            :value="filters.startDate"
            :disabled="loading"
            @input="updateFilters({ startDate: $event.target.value })"
          />
        </div>

        <div class="filter-field">
          <label for="msd-end-date">結束</label>
          <input
            id="msd-end-date"
            type="date"
            :value="filters.endDate"
            :disabled="loading"
            @input="updateFilters({ endDate: $event.target.value })"
          />
        </div>

        <div class="filter-field">
          <label>不良原因</label>
          <MultiSelect
            :model-value="filters.lossReasons"
            :options="availableLossReasons"
            :disabled="loading"
            placeholder="全部原因"
            @update:model-value="updateFilters({ lossReasons: $event })"
          />
        </div>

        <button
          type="button"
          class="btn btn-primary"
          :disabled="loading"
          @click="$emit('query')"
        >
          查詢
        </button>
      </div>
    </div>
  </section>
</template>
