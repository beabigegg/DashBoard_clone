<script setup lang="ts">
import { computed, ref } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

// Closed enum per UPH-02 — no other family prefix is ever valid for this page.
const FAMILY_OPTIONS = Object.freeze(['GDBA', 'GWBA']);

interface CoarseFilter {
  date_from: string;
  date_to: string;
  families: string[];
  workcenter_names: string[];
  packages: string[];
  pj_types: string[];
  equipment_ids: string[];
}

interface ProductFilterOptions {
  pj_types: string[];
  product_lines: string[];
}

interface LoadingState {
  querying?: boolean;
  [key: string]: unknown;
}

const props = defineProps<{
  filters: CoarseFilter;
  productFilterOptions: ProductFilterOptions;
  loading: LoadingState;
  productOptionsLoading?: boolean;
  productOptionsError?: string;
}>();

const emit = defineEmits<{
  (e: 'submit'): void;
  (e: 'clear'): void;
  (e: 'update:filters', value: CoarseFilter): void;
}>();

// ── Free-text multi-value entry (no pre-query options endpoint exists for
//    workcenter_names / equipment_ids in the API contract — mirrors
//    eap-alarm's LOT ID textarea pattern) ──────────────────────────────────
const workcenterRaw = ref('');
const equipmentRaw = ref('');

function parseLines(raw: string): string[] {
  return raw
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
}

function onWorkcenterBlur() {
  emit('update:filters', { ...props.filters, workcenter_names: parseLines(workcenterRaw.value) });
}

function onEquipmentBlur() {
  emit('update:filters', { ...props.filters, equipment_ids: parseLines(equipmentRaw.value) });
}

function handleSubmit() {
  // Sync free-text fields from their textareas in case blur didn't fire yet.
  emit('update:filters', {
    ...props.filters,
    workcenter_names: parseLines(workcenterRaw.value),
    equipment_ids: parseLines(equipmentRaw.value),
  });
  emit('submit');
}

function handleClear() {
  workcenterRaw.value = '';
  equipmentRaw.value = '';
  emit('update:filters', {
    ...props.filters,
    families: [],
    workcenter_names: [],
    packages: [],
    pj_types: [],
    equipment_ids: [],
  });
  emit('clear');
}

// UPH-only rule: date range is the sole required input (no at-least-one-of-N
// rule — families empty means "both", per UPH-02).
const canSubmit = computed(() =>
  !props.loading.querying &&
  !!props.filters.date_from &&
  !!props.filters.date_to &&
  props.filters.date_from <= props.filters.date_to
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
        <label class="filter-label" for="uph-date-from">開始日期 <span class="filter-required">*</span></label>
        <input
          id="uph-date-from"
          v-model="filters.date_from"
          type="date"
          class="filter-input"
          data-testid="start-date"
          required
        />
      </div>
      <div class="filter-group">
        <label class="filter-label" for="uph-date-to">結束日期 <span class="filter-required">*</span></label>
        <input
          id="uph-date-to"
          v-model="filters.date_to"
          type="date"
          class="filter-input"
          data-testid="end-date"
          required
        />
      </div>

      <!-- Family (GDBA/GWBA only — confirmed #7: no static DB/WB gloss here) -->
      <div class="filter-group">
        <label class="filter-label">機型</label>
        <MultiSelect
          :model-value="filters.families"
          :options="FAMILY_OPTIONS"
          placeholder="全部 (GDBA/GWBA)"
          data-testid="ctrl-family-select"
          @update:model-value="(v: string[]) => emit('update:filters', { ...filters, families: v })"
        />
      </div>

      <!-- Workcenter (free-text, no pre-query options endpoint) -->
      <div class="filter-group filter-group-wide">
        <label class="filter-label" for="uph-workcenter">工作站 / WORKCENTERNAME</label>
        <textarea
          id="uph-workcenter"
          v-model="workcenterRaw"
          class="filter-input filter-textarea"
          :disabled="loading.querying"
          placeholder="每行一個工作站名稱 / One WORKCENTERNAME per line"
          rows="2"
          data-testid="ctrl-workcenter-select"
          @blur="onWorkcenterBlur"
        />
      </div>

      <!-- Equipment ID (free-text, max 200) -->
      <div class="filter-group filter-group-wide">
        <label class="filter-label" for="uph-equipment">機台 ID / EQUIPMENT_ID</label>
        <textarea
          id="uph-equipment"
          v-model="equipmentRaw"
          class="filter-input filter-textarea"
          :disabled="loading.querying"
          placeholder="每行一個機台 ID，最多 200 筆 / One EQUIPMENT_ID per line, max 200"
          rows="2"
          data-testid="ctrl-equipment-search"
          @blur="onEquipmentBlur"
        />
      </div>

      <!-- Package (product_lines) -->
      <div class="filter-group">
        <label class="filter-label">Package / 封裝</label>
        <MultiSelect
          :model-value="filters.packages"
          :options="productFilterOptions.product_lines"
          :disabled="loading.querying || productOptionsLoading"
          :placeholder="productOptionsLoading ? '載入中...' : '全部 Package'"
          searchable
          data-testid="ctrl-package-select"
          @update:model-value="(v: string[]) => emit('update:filters', { ...filters, packages: v })"
        />
      </div>

      <!-- Type (global scope — feeds the spool key; visibly distinct from the
           ranking block's own independent Type filter) -->
      <div class="filter-group">
        <label class="filter-label">Type / 全域類型</label>
        <MultiSelect
          :model-value="filters.pj_types"
          :options="productFilterOptions.pj_types"
          :disabled="loading.querying || productOptionsLoading"
          :placeholder="productOptionsLoading ? '載入中...' : '全部 Type'"
          searchable
          data-testid="ctrl-type-select-global"
          @update:model-value="(v: string[]) => emit('update:filters', { ...filters, pj_types: v })"
        />
      </div>

      <!-- Confirmed #6: product-filter-options 500 -> inline warning; other
           filters remain usable (state-coarse-options-degraded) -->
      <div v-if="productOptionsError" class="filter-group-full product-options-warning" data-testid="product-options-warning" role="alert">
        Package / Type 選項載入失敗，其餘篩選器仍可使用：{{ productOptionsError }}
      </div>

      <!-- Toolbar -->
      <div class="filter-toolbar filter-group-full">
        <div class="filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            data-testid="ctrl-submit"
            :disabled="!canSubmit"
            :title="!canSubmit ? '請填入開始與結束日期' : ''"
            @click="handleSubmit"
          >
            <template v-if="loading.querying">查詢中...</template>
            <template v-else>查詢</template>
          </button>
          <button
            type="button"
            class="ui-btn ui-btn--ghost"
            data-testid="ctrl-clear"
            :disabled="loading.querying"
            @click="handleClear"
          >
            清除
          </button>
        </div>
        <div class="filter-hint">
          日期為必填；機型 / 工作站 / Package / Type / 機台 ID 皆為選填（留空代表全部）。
        </div>
      </div>
    </div>
  </section>
</template>
