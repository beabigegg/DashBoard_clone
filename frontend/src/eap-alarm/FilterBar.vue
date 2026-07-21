<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
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
  lot_ids: string[];
  work_orders: string[];
  pj_types: string[];
  product_lines: string[];
  pj_bops: string[];
}

interface ProductFilterOptions {
  pj_types: string[];
  product_lines: string[];
  pj_bops: string[];
  updated_at: string | null;
}

interface LoadingState {
  querying?: boolean;
  [key: string]: unknown;
}

const props = withDefaults(defineProps<{
  filters: CoarseFilter;
  queryMode?: 'date_range' | 'lot_ids';
  resourceOptions: ResourceOptions;
  productFilterOptions: ProductFilterOptions;
  loading: LoadingState;
  productOptionsLoading?: boolean;
}>(), {
  queryMode: 'date_range',
});

const emit = defineEmits<{
  (e: 'submit'): void;
  (e: 'clear'): void;
  (e: 'update:queryMode', value: 'date_range' | 'lot_ids'): void;
  (e: 'update:filters', value: CoarseFilter): void;
}>();

// ── LOT ID textarea local state ───────────────────────────────────────────────
const lotIdRaw = ref('');

function onLotIdBlur() {
  const parsedIds = lotIdRaw.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  emit('update:filters', { ...props.filters, lot_ids: parsedIds });
}

// ── Work order textarea local state ───────────────────────────────────────────
const workOrderRaw = ref('');

function onWorkOrderBlur() {
  const parsed = workOrderRaw.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
  emit('update:filters', { ...props.filters, work_orders: parsed });
}

function setQueryMode(mode: 'date_range' | 'lot_ids') {
  if (mode === props.queryMode) return;
  lotIdRaw.value = '';
  workOrderRaw.value = '';
  emit('update:filters', { ...props.filters, lot_ids: [], work_orders: [] });
  emit('update:queryMode', mode);
}

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
  emit('update:filters', { ...props.filters, machines: [] });
}
function updateMachines(v: string[]) {
  emit('update:filters', { ...props.filters, machines: v });
}

// Submit: parse LOT IDs from textarea (in case blur didn't fire), then emit
function handleSubmit() {
  // Sync lot_ids from textarea before submit
  const parsedIds = lotIdRaw.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

  // Sync work_orders from textarea before submit (lot_ids mode only)
  const parsedWorkOrders = workOrderRaw.value
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);

  // D-8: a family ("型號") selected without any specific machine ("機台")
  // must not silently drop the family-level filter. Expand `machines` to
  // every name in the already-loaded, family-filtered machineOptions pool
  // before emitting. Specific-machine selections and no-family selections
  // are left unchanged (client-side only; cascade.families itself is never
  // sent to the backend).
  const machines =
    cascade.families.length > 0 && (props.filters.machines?.length ?? 0) === 0
      ? [...machineOptions.value]
      : props.filters.machines;

  emit('update:filters', {
    ...props.filters,
    lot_ids: props.queryMode === 'lot_ids' ? parsedIds : [],
    work_orders: props.queryMode === 'lot_ids' ? parsedWorkOrders : [],
    machines,
  });
  // Use nextTick-like approach: emit submit after filter update propagates
  // (parent's Object.assign is synchronous so emit order is sufficient)
  emit('submit');
}

function handleClear() {
  cascade.families = [];
  lotIdRaw.value = '';
  workOrderRaw.value = '';
  emit('update:filters', {
    ...props.filters,
    machines: [],
    lot_ids: [],
    work_orders: [],
    pj_types: [],
    product_lines: [],
    pj_bops: [],
  });
  emit('clear');
}

// ── hasLotIds: checks textarea raw value OR already-parsed lot_ids ──────────
const hasLotIds = computed(() =>
  props.filters.lot_ids?.length > 0 || lotIdRaw.value.trim().length > 0
);

const canSubmit = computed(() =>
  !props.loading.querying && (
    props.queryMode === 'lot_ids'
      ? hasLotIds.value
      : !!props.filters.date_from &&
        !!props.filters.date_to &&
        (
          (props.filters.machines?.length ?? 0) > 0 ||
          cascade.families.length > 0 ||
          (props.filters.pj_types?.length ?? 0) > 0 ||
          (props.filters.product_lines?.length ?? 0) > 0 ||
          (props.filters.pj_bops?.length ?? 0) > 0
        )
  )
);
</script>

<template>
  <section class="card ui-card filter-query-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">查詢條件</div>
    </div>
    <div class="card-body ui-card-body filter-panel">
      <div class="filter-group-full mode-tab-row">
        <button
          type="button"
          data-testid="query-mode-date"
          :class="['mode-tab', { active: queryMode === 'date_range' }]"
          :disabled="loading.querying"
          @click="setQueryMode('date_range')"
        >
          日期區間
        </button>
        <button
          type="button"
          data-testid="query-mode-lot"
          :class="['mode-tab', { active: queryMode === 'lot_ids' }]"
          :disabled="loading.querying"
          @click="setQueryMode('lot_ids')"
        >
          指定 LOT
        </button>
      </div>

      <!-- 型號 cascade filter (shown in both modes) -->
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

      <!-- 機台 (filtered by 型號 + flags; shown in both modes) -->
      <div class="filter-group filter-group-wide">
      <label class="filter-label">機台</label>
      <MultiSelect
        :model-value="filters.machines"
        :options="machineOptions"
        :disabled="loading.querying"
        placeholder="全部篩選後機台"
        searchable
        data-testid="machine-select"
        @update:model-value="updateMachines"
      />
      </div>

      <template v-if="queryMode === 'date_range'">
        <div class="filter-group">
          <label class="filter-label" for="eap-date-from">開始日期 <span class="filter-required">*</span></label>
          <input
            id="eap-date-from"
            v-model="filters.date_from"
            type="date"
            class="filter-input"
            data-testid="start-date"
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
            data-testid="end-date"
            required
          />
        </div>

        <!-- Type -->
        <div class="filter-group">
        <label class="filter-label">Type</label>
        <MultiSelect
          :model-value="filters.pj_types"
          :options="productFilterOptions.pj_types"
          :disabled="loading.querying || productOptionsLoading"
          :placeholder="productOptionsLoading ? '載入中...' : '全部 Type'"
          searchable
          data-testid="pj-type-select"
          @update:model-value="(v: string[]) => emit('update:filters', { ...filters, pj_types: v })"
        />
        </div>

        <!-- Package -->
        <div class="filter-group">
        <label class="filter-label">Package</label>
        <MultiSelect
          :model-value="filters.product_lines"
          :options="productFilterOptions.product_lines"
          :disabled="loading.querying || productOptionsLoading"
          :placeholder="productOptionsLoading ? '載入中...' : '全部 Package'"
          searchable
          data-testid="product-line-select"
          @update:model-value="(v: string[]) => emit('update:filters', { ...filters, product_lines: v })"
        />
        </div>

        <!-- BOP -->
        <div class="filter-group">
        <label class="filter-label">BOP</label>
        <MultiSelect
          :model-value="filters.pj_bops"
          :options="productFilterOptions.pj_bops"
          :disabled="loading.querying || productOptionsLoading"
          :placeholder="productOptionsLoading ? '載入中...' : '全部 BOP'"
          searchable
          data-testid="pj-bop-select"
          @update:model-value="(v: string[]) => emit('update:filters', { ...filters, pj_bops: v })"
        />
        </div>
      </template>

      <template v-else>
        <div class="filter-group filter-group-full">
          <label class="filter-label" for="eap-lot-id">LOT ID</label>
          <textarea
            id="eap-lot-id"
            v-model="lotIdRaw"
            class="filter-input filter-textarea"
            :disabled="loading.querying"
            placeholder="每行一個 LOT ID / One LOT ID per line"
            rows="4"
            data-testid="lot-id-textarea"
            @blur="onLotIdBlur"
          />
          <span class="filter-hint">指定 LOT 查詢不需填寫日期。</span>
        </div>

        <div class="filter-group filter-group-full">
          <label class="filter-label" for="eap-work-order">工單號</label>
          <textarea
            id="eap-work-order"
            v-model="workOrderRaw"
            class="filter-input filter-textarea"
            :disabled="loading.querying"
            placeholder="每行一個工單號 / One work order per line（選填）"
            rows="3"
            data-testid="work-order-textarea"
            @blur="onWorkOrderBlur"
          />
          <span class="filter-hint">選填，最多 200 筆。</span>
        </div>
      </template>

      <!-- Toolbar -->
      <div class="filter-toolbar filter-group-full">
        <div class="filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            data-testid="coarse-submit-btn"
            :disabled="!canSubmit"
            :title="!canSubmit ? (queryMode === 'lot_ids' ? '請至少輸入一個 LOT ID' : '請選擇至少一項：機台、Type、Package 或 BOP') : ''"
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
          <template v-if="queryMode === 'date_range'">
            日期為必填；機台、Type、Package、BOP 至少填入一項。
          </template>
          <template v-else>每行一個 LOT ID，最多 200 筆。</template>
        </div>
      </div>
    </div>
  </section>
</template>
