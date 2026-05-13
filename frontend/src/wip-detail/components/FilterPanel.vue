<script setup lang="ts">
import { reactive, watch } from 'vue';

import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

const props = defineProps({
  filters: {
    type: Object,
    required: true,
  },
  options: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['apply', 'clear', 'draft-change']);

const fields = [
  { key: 'workorder', label: 'WORKORDER', optionKey: 'workorders', placeholder: 'All WORKORDER' },
  { key: 'lotid', label: 'LOT ID', optionKey: 'lotids', placeholder: 'All LOT ID' },
  { key: 'package', label: 'PACKAGE', optionKey: 'packages', placeholder: 'All PACKAGE' },
  { key: 'type', label: 'TYPE', optionKey: 'types', placeholder: 'All TYPE' },
  { key: 'firstname', label: 'Wafer LOT', optionKey: 'firstnames', placeholder: 'All Wafer LOT' },
  { key: 'waferdesc', label: 'Wafer Type', optionKey: 'waferdescs', placeholder: 'All Wafer Type' },
];

type DraftFilters = {
  workorder: string[];
  lotid: string[];
  package: string[];
  type: string[];
  firstname: string[];
  waferdesc: string[];
};

const draft = reactive<DraftFilters>({
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
});

function toArray(value: unknown): string[] {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  return String(value)
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function cloneDraft() {
  return {
    workorder: [...draft.workorder],
    lotid: [...draft.lotid],
    package: [...draft.package],
    type: [...draft.type],
    firstname: [...draft.firstname],
    waferdesc: [...draft.waferdesc],
  };
}

watch(
  () => props.filters,
  (nextFilters) => {
    draft.workorder = toArray(nextFilters.workorder);
    draft.lotid = toArray(nextFilters.lotid);
    draft.package = toArray(nextFilters.package);
    draft.type = toArray(nextFilters.type);
    draft.firstname = toArray(nextFilters.firstname);
    draft.waferdesc = toArray(nextFilters.waferdesc);
  },
  { immediate: true, deep: true }
);

function getOptions(field: { key: string; label: string; optionKey: string; placeholder: string }): string[] {
  const opts = (props.options as Record<string, unknown>)?.[field.optionKey];
  return Array.isArray(opts) ? (opts as string[]) : [];
}

function getDraftField(key: string): string[] {
  return (draft as Record<string, string[]>)[key] ?? [];
}

function setDraftField(key: string, value: string[]): void {
  (draft as Record<string, string[]>)[key] = value;
}

function notifyDraftChange() {
  emit('draft-change', cloneDraft());
}

function applyFilters() {
  emit('apply', cloneDraft());
}

function clearFilters() {
  draft.workorder = [];
  draft.lotid = [];
  draft.package = [];
  draft.type = [];
  draft.firstname = [];
  draft.waferdesc = [];
  notifyDraftChange();
  emit('clear');
}
</script>

<template>
  <section class="filters">
    <div v-for="field in fields" :key="field.key" class="filter-group">
      <label>{{ field.label }}</label>
      <MultiSelect
        :model-value="getDraftField(field.key)"
        :options="getOptions(field)"
        :disabled="loading"
        :placeholder="field.placeholder"
        searchable
        @update:model-value="
          setDraftField(field.key, $event);
          notifyDraftChange();
        "
      />
    </div>

    <div class="filters-actions">
      <button type="button" class="ui-btn ui-btn--primary" :disabled="loading" @click="applyFilters">套用篩選</button>
      <button type="button" class="ui-btn ui-btn--ghost" :disabled="loading" @click="clearFilters">清除篩選</button>
    </div>
  </section>
</template>
