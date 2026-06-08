<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';

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
  lastUpdate: {
    type: String,
    default: '',
  },
  refreshing: {
    type: Boolean,
    default: false,
  },
  refreshSuccess: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['apply', 'clear', 'draft-change']);

// Row 1: WORKORDER / LOT ID / PACKAGE
// Row 2: WORKFLOW / BOP / TYPE
// Row 3: FUNCTION / Wafer LOT / Wafer Type
const fields = [
  { key: 'workorder',   label: 'WORKORDER',  optionKey: 'workorders',   placeholder: '全部 WORKORDER' },
  { key: 'lotid',       label: 'LOT ID',     optionKey: 'lotids',       placeholder: '全部 LOT ID' },
  { key: 'package',     label: 'PACKAGE',    optionKey: 'packages',     placeholder: '全部 PACKAGE' },
  { key: 'workflow',    label: 'WORKFLOW',   optionKey: 'workflows',    placeholder: '全部 WORKFLOW' },
  { key: 'bop',         label: 'BOP',        optionKey: 'bops',         placeholder: '全部 BOP' },
  { key: 'type',        label: 'TYPE',       optionKey: 'types',        placeholder: '全部 TYPE' },
  { key: 'pjFunction',  label: 'FUNCTION',   optionKey: 'pjFunctions',  placeholder: '全部 FUNCTION' },
  { key: 'firstname',   label: 'Wafer LOT',  optionKey: 'firstnames',   placeholder: '全部 Wafer LOT' },
  { key: 'waferdesc',   label: 'Wafer Type', optionKey: 'waferdescs',   placeholder: '全部 Wafer Type' },
];

type DraftFilters = {
  workorder: string[];
  lotid: string[];
  package: string[];
  type: string[];
  firstname: string[];
  waferdesc: string[];
  workflow: string[];
  bop: string[];
  pjFunction: string[];
};

const draft = reactive<DraftFilters>({
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
  workflow: [],
  bop: [],
  pjFunction: [],
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
    workflow: [...draft.workflow],
    bop: [...draft.bop],
    pjFunction: [...draft.pjFunction],
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
    draft.workflow = toArray(nextFilters.workflow);
    draft.bop = toArray(nextFilters.bop);
    draft.pjFunction = toArray(nextFilters.pjFunction);
  },
  { immediate: true, deep: true }
);

function getOptions(field: { key: string; label: string; optionKey: string; placeholder: string }): string[] {
  const opts = (props.options as Record<string, unknown>)?.[field.optionKey];
  return Array.isArray(opts) ? (opts as string[]) : [];
}

function applyFilters() {
  emit('apply', cloneDraft());
}

function notifyDraftChange() {
  emit('draft-change', cloneDraft());
}

function clearFilters() {
  draft.workorder = [];
  draft.lotid = [];
  draft.package = [];
  draft.type = [];
  draft.firstname = [];
  draft.waferdesc = [];
  draft.workflow = [];
  draft.bop = [];
  draft.pjFunction = [];
  notifyDraftChange();
  emit('clear');
}

function getDraftField(key: string): string[] {
  return (draft as Record<string, string[]>)[key] ?? [];
}

function setDraftField(key: string, value: string[]): void {
  (draft as Record<string, string[]>)[key] = value;
}

const collapsed = ref(true);

const activeFilterCount = computed(() => {
  const filterKeys = ['workorder', 'lotid', 'package', 'type', 'firstname', 'waferdesc', 'workflow', 'bop', 'pjFunction'] as const;
  return filterKeys.filter((key) => (props.filters as Record<string, string[]>)[key]?.length > 0).length;
});

function toggleCollapse() {
  collapsed.value = !collapsed.value;
}
</script>

<template>
  <section class="filters-section">
    <div class="filters-toggle" role="button" tabindex="0" @click="toggleCollapse" @keydown.enter="toggleCollapse" @keydown.space.prevent="toggleCollapse">
      <div class="filters-toggle-left">
        <span class="filters-toggle-icon" :class="{ expanded: !collapsed }">&#9654;</span>
        <span class="filters-toggle-label">篩選條件</span>
        <span v-if="activeFilterCount > 0" class="filters-active-badge">{{ activeFilterCount }}</span>
      </div>
      <div class="filters-toggle-right">
        <button
          v-if="activeFilterCount > 0"
          type="button"
          class="ui-btn ui-btn--ghost ui-btn--sm filters-clear-btn"
          :disabled="loading"
          @click.stop="clearFilters"
        >清除篩選</button>
        <span v-if="refreshing" class="refresh-indicator active"></span>
        <span v-else-if="refreshSuccess" class="refresh-success active">&#10003;</span>
        <span v-if="lastUpdate" class="filters-last-update">更新: {{ lastUpdate }}</span>
      </div>
    </div>

    <div v-show="!collapsed" class="filters-body">
      <div class="filters-grid">
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
              applyFilters();
            "
          />
        </div>
      </div>
    </div>
  </section>
</template>
