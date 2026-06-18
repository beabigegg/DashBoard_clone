<script setup lang="ts">
import { computed, reactive } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface ResourceOption {
  id: string;
  name: string;
  family: string;
  workcenterGroup: string;
}

interface ResourceOptions {
  families: string[];
  resources: ResourceOption[];
}

interface CoarseFilter {
  date_from: string;
  date_to: string;
  machines: string[];
}

interface LoadingState {
  querying?: boolean;
  [key: string]: unknown;
}

const props = defineProps<{
  filters: CoarseFilter;
  resourceOptions: ResourceOptions;
  loading: LoadingState;
}>();

const emit = defineEmits<{
  (e: 'submit'): void;
  (e: 'clear'): void;
}>();

// ── Cascade state (local; determines the machine options pool) ───────────────
const cascade = reactive({
  families: [] as string[],
});

// ── Derived machine pool from cascade ────────────────────────────────────────
const filteredResources = computed<ResourceOption[]>(() => {
  const list = props.resourceOptions.resources ?? [];
  if (cascade.families.length === 0) return list;
  const fset = new Set(cascade.families);
  return list.filter(r => fset.has(r.family));
});

const machineOptions = computed(() =>
  filteredResources.value
    .map(r => r.name)
    .sort((a, b) => a.localeCompare(b))
);

function updateFamilies(v: string[]) {
  cascade.families = v;
  props.filters.machines = [];
}
function updateMachines(v: string[]) {
  props.filters.machines = v;
}

// Submit: if no machines explicitly selected, use all filtered
function handleSubmit() {
  if (props.filters.machines.length === 0) {
    props.filters.machines = [...machineOptions.value];
  }
  emit('submit');
}

function handleClear() {
  cascade.families = [];
  props.filters.machines = [];
  emit('clear');
}

const canSubmit = computed(() =>
  !props.loading.querying &&
  !!props.filters.date_from &&
  !!props.filters.date_to
);
</script>

<template>
  <section class="card ui-card filter-query-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">查詢條件</div>
    </div>
    <div class="card-body ui-card-body filter-panel">
      <!-- Date range -->
      <div class="filter-group">
        <label class="filter-label" for="eap-date-from">開始日期 <span class="filter-required">*</span></label>
        <input
          id="eap-date-from"
          v-model="filters.date_from"
          type="date"
          class="filter-input"
          required
        />
      </div>
      <div class="filter-group">
        <label class="filter-label" for="eap-date-to">結束日期 <span class="filter-required">*</span></label>
        <input
          id="eap-date-to"
          v-model="filters.date_to"
          type="date"
          class="filter-input"
          required
        />
      </div>

      <!-- 型號 cascade filter -->
      <div class="filter-group">
        <label class="filter-label">型號</label>
        <MultiSelect
          :model-value="cascade.families"
          :options="resourceOptions.families"
          :disabled="loading.querying"
          placeholder="全部型號"
          searchable
          @update:model-value="updateFamilies"
        />
      </div>

      <!-- 機台 (filtered by 型號 + flags) -->
      <div class="filter-group filter-group-wide">
        <label class="filter-label">機台</label>
        <MultiSelect
          :model-value="filters.machines"
          :options="machineOptions"
          :disabled="loading.querying"
          placeholder="全部篩選後機台"
          searchable
          @update:model-value="updateMachines"
        />
      </div>

      <!-- Toolbar -->
      <div class="filter-toolbar filter-group-full">
        <div class="filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            :disabled="!canSubmit"
            @click="handleSubmit"
          >
            <template v-if="loading.querying">查詢中...</template>
            <template v-else>查詢</template>
          </button>
          <button
            type="button"
            class="ui-btn ui-btn--ghost"
            :disabled="loading.querying"
            @click="handleClear"
          >
            清除條件
          </button>
        </div>
        <div class="filter-hint">
          日期為必填。可選型號或機台縮小查詢範圍；不選機台則查詢全部篩選結果。
        </div>
      </div>
    </div>
  </section>
</template>
