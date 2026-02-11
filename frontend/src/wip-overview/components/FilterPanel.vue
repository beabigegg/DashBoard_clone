<script setup>
import { reactive, watch } from 'vue';

import { apiGet } from '../../core/api.js';
import { useAutocomplete } from '../../shared-composables/useAutocomplete.js';

const props = defineProps({
  filters: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(['apply', 'clear', 'remove']);

const draft = reactive({
  workorder: '',
  lotid: '',
  package: '',
  type: '',
});

watch(
  () => props.filters,
  (nextFilters) => {
    draft.workorder = nextFilters.workorder || '';
    draft.lotid = nextFilters.lotid || '';
    draft.package = nextFilters.package || '';
    draft.type = nextFilters.type || '';
  },
  { immediate: true, deep: true }
);

const { ensureField, handleInput, handleFocus, handleBlur, selectItem } = useAutocomplete({
  getFilters: () => ({ ...draft }),
  request: (url, options) => apiGet(url, options),
  debounceMs: 300,
});

const fields = [
  { key: 'workorder', label: 'WORKORDER', placeholder: '輸入 WORKORDER...' },
  { key: 'lotid', label: 'LOT ID', placeholder: '輸入 LOT ID...' },
  { key: 'package', label: 'PACKAGE', placeholder: '輸入 PACKAGE...' },
  { key: 'type', label: 'TYPE', placeholder: '輸入 TYPE...' },
];

function getFieldState(field) {
  return ensureField(field);
}

function applyFilters() {
  emit('apply', { ...draft });
}

function clearFilters() {
  draft.workorder = '';
  draft.lotid = '';
  draft.package = '';
  draft.type = '';
  emit('clear');
}

function removeFilter(field) {
  draft[field] = '';
  emit('remove', field);
}

function onInput(field, event) {
  draft[field] = event.target.value;
  handleInput(field, draft[field]);
}

function onSelect(field, value) {
  draft[field] = selectItem(field, value);
}
</script>

<template>
  <section class="filters">
    <div v-for="field in fields" :key="field.key" class="filter-group">
      <label>{{ field.label }}</label>
      <input
        type="text"
        :value="draft[field.key]"
        :placeholder="field.placeholder"
        autocomplete="off"
        @input="onInput(field.key, $event)"
        @focus="handleFocus(field.key)"
        @blur="handleBlur(field.key)"
        @keydown.enter.prevent="applyFilters"
      />
      <span class="search-loading" :class="{ active: getFieldState(field.key).loading }"></span>
      <div class="autocomplete-dropdown" :class="{ active: getFieldState(field.key).open }">
        <div
          v-for="item in getFieldState(field.key).items"
          :key="item"
          class="autocomplete-item"
          @mousedown.prevent="onSelect(field.key, item)"
        >
          {{ item }}
        </div>
        <div
          v-if="!getFieldState(field.key).loading && getFieldState(field.key).open && getFieldState(field.key).items.length === 0"
          class="autocomplete-item no-results"
        >
          無符合結果
        </div>
      </div>
    </div>

    <button type="button" class="btn-primary" @click="applyFilters">套用篩選</button>
    <button type="button" class="btn-secondary" @click="clearFilters">清除篩選</button>

    <TransitionGroup name="filter-chip" tag="div" class="active-filters">
      <span v-if="filters.workorder" key="workorder" class="filter-tag">
        WO: {{ filters.workorder }}
        <span class="remove" @click="removeFilter('workorder')">×</span>
      </span>
      <span v-if="filters.lotid" key="lotid" class="filter-tag">
        Lot: {{ filters.lotid }}
        <span class="remove" @click="removeFilter('lotid')">×</span>
      </span>
      <span v-if="filters.package" key="package" class="filter-tag">
        Pkg: {{ filters.package }}
        <span class="remove" @click="removeFilter('package')">×</span>
      </span>
      <span v-if="filters.type" key="type" class="filter-tag">
        Type: {{ filters.type }}
        <span class="remove" @click="removeFilter('type')">×</span>
      </span>
    </TransitionGroup>
  </section>
</template>
