<script setup>
import { reactive, watch } from 'vue';

import { apiGet } from '../../core/api.js';
import { useAutocomplete } from '../../wip-shared/composables/useAutocomplete.js';

const props = defineProps({
  filters: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(['apply', 'clear']);

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
  { key: 'workorder', label: 'WORKORDER', placeholder: 'Search...' },
  { key: 'lotid', label: 'LOT ID', placeholder: 'Search...' },
  { key: 'package', label: 'PACKAGE', placeholder: 'Search...' },
  { key: 'type', label: 'TYPE', placeholder: 'Search...' },
];

function getFieldState(field) {
  return ensureField(field);
}

function onInput(field, event) {
  draft[field] = event.target.value;
  handleInput(field, draft[field]);
}

function onSelect(field, value) {
  draft[field] = selectItem(field, value);
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
</script>

<template>
  <section class="filters">
    <div v-for="field in fields" :key="field.key" class="filter-group">
      <label>{{ field.label }}</label>
      <div class="autocomplete-container">
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
        <div class="autocomplete-dropdown" :class="{ show: getFieldState(field.key).open }">
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
            class="autocomplete-empty"
          >
            No results
          </div>
        </div>
      </div>
    </div>

    <button type="button" class="btn-primary" @click="applyFilters">Apply</button>
    <button type="button" class="btn-secondary" @click="clearFilters">Clear</button>
  </section>
</template>
