<script setup>
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

const GRANULARITY_ITEMS = [
  { key: 'day', label: '日' },
  { key: 'week', label: '週' },
  { key: 'month', label: '月' },
  { key: 'year', label: '年' },
];

const props = defineProps({
  filters: {
    type: Object,
    required: true,
  },
  options: {
    type: Object,
    default: () => ({
      workcenterGroups: [],
      families: [],
    }),
  },
  machineOptions: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['update-filters', 'query', 'clear']);

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
          <label for="history-start-date">開始</label>
          <input
            id="history-start-date"
            type="date"
            :value="filters.startDate"
            :disabled="loading"
            @input="updateFilters({ startDate: $event.target.value })"
          />
        </div>

        <div class="filter-field">
          <label for="history-end-date">結束</label>
          <input
            id="history-end-date"
            type="date"
            :value="filters.endDate"
            :disabled="loading"
            @input="updateFilters({ endDate: $event.target.value })"
          />
        </div>

        <div class="filter-field">
          <label>粒度</label>
          <div class="granularity-btns">
            <button
              v-for="item in GRANULARITY_ITEMS"
              :key="item.key"
              type="button"
              class="granularity-btn"
              :class="{ active: filters.granularity === item.key }"
              :disabled="loading"
              @click="updateFilters({ granularity: item.key })"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div class="filter-field">
          <label>工站群組</label>
          <MultiSelect
            :model-value="filters.workcenterGroups"
            :options="options.workcenterGroups"
            :disabled="loading"
            placeholder="全部站點"
            @update:model-value="updateFilters({ workcenterGroups: $event })"
          />
        </div>

        <div class="filter-field">
          <label>型號</label>
          <MultiSelect
            :model-value="filters.families"
            :options="options.families"
            :disabled="loading"
            placeholder="全部型號"
            @update:model-value="updateFilters({ families: $event })"
          />
        </div>

        <div class="filter-field">
          <label>機台</label>
          <MultiSelect
            :model-value="filters.machines"
            :options="machineOptions"
            :disabled="loading"
            placeholder="全部機台"
            searchable
            @update:model-value="updateFilters({ machines: $event })"
          />
        </div>

        <div class="checkbox-row">
          <label class="checkbox-pill">
            <input
              type="checkbox"
              :checked="filters.isProduction"
              :disabled="loading"
              @change="updateFilters({ isProduction: $event.target.checked })"
            />
            生產設備
          </label>
          <label class="checkbox-pill">
            <input
              type="checkbox"
              :checked="filters.isKey"
              :disabled="loading"
              @change="updateFilters({ isKey: $event.target.checked })"
            />
            重點設備
          </label>
          <label class="checkbox-pill">
            <input
              type="checkbox"
              :checked="filters.isMonitor"
              :disabled="loading"
              @change="updateFilters({ isMonitor: $event.target.checked })"
            />
            監控設備
          </label>
        </div>

        <button type="button" class="ui-btn ui-btn--primary" :disabled="loading" @click="$emit('query')">查詢</button>
        <button type="button" class="ui-btn ui-btn--ghost" :disabled="loading" @click="$emit('clear')">清除條件</button>
      </div>
    </div>
  </section>
</template>
