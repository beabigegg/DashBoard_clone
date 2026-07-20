<script setup lang="ts">
import { computed } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface MachineRow {
  equipment_id: string;
  family: string;
  model: string | null;
  workcenter: string | null;
}
interface MachineOptions {
  families: { code: string; label: string }[];
  models: { family: string; model: string }[];
  workcenters: string[];
  equipment: MachineRow[];
}

interface CoarseFilter {
  date_from: string;
  date_to: string;
  families: string[];        // DB/WB category (GDBA/GWBA)
  models: string[];          // 機型 (RESOURCEFAMILYNAME)
  workcenter_names: string[];
  packages: string[];
  pj_types: string[];
  equipment_ids: string[];
}

interface LoadingState {
  querying?: boolean;
  [key: string]: unknown;
}

const props = defineProps<{
  filters: CoarseFilter;
  machineOptions: MachineOptions;
  machineOptionsLoading?: boolean;
  machineOptionsError?: string;
  loading: LoadingState;
}>();

const emit = defineEmits<{
  (e: 'submit'): void;
  (e: 'clear'): void;
  (e: 'update:filters', value: CoarseFilter): void;
}>();

// ── Cascade (machine-options): family (DB/WB) -> model -> workcenter -> equipment ──
// Each dropdown's options are constrained by the UPSTREAM selections only; an
// empty upstream selection means "all". Downstream selections are pruned in the
// change handlers below so an invalid combination can never survive a change.
function matchRows(families: string[], models: string[], workcenters: string[]): MachineRow[] {
  return (props.machineOptions.equipment || []).filter((r) =>
    (families.length === 0 || families.includes(r.family)) &&
    (models.length === 0 || (r.model != null && models.includes(r.model))) &&
    (workcenters.length === 0 || (r.workcenter != null && workcenters.includes(r.workcenter))),
  );
}
function distinct<T>(xs: (T | null | undefined)[]): T[] {
  return [...new Set(xs.filter((x): x is T => x != null && x !== ''))];
}

// DB/WB category options: value = GDBA/GWBA code, label = 分類 (GDBA)
const familyOptions = computed(() =>
  (props.machineOptions.families || []).map((f) => ({ label: `${f.label} (${f.code})`, value: f.code })),
);
// 機型: constrained by selected families; sorted.
const modelOptions = computed(() =>
  distinct(matchRows(props.filters.families, [], []).map((r) => r.model)).sort(),
);
// 工作站: constrained by families + models.
const workcenterOptions = computed(() =>
  distinct(matchRows(props.filters.families, props.filters.models, []).map((r) => r.workcenter)).sort(),
);
// 機台: constrained by families + models + workcenters.
const equipmentOptions = computed(() =>
  distinct(
    matchRows(props.filters.families, props.filters.models, props.filters.workcenter_names).map((r) => r.equipment_id),
  ).sort(),
);

// Change handlers prune every downstream axis to values still reachable under
// the new upstream selection (so the spool never receives a mutually-exclusive
// combination the user can no longer see).
function onFamiliesChange(families: string[]) {
  const validModels = new Set(distinct(matchRows(families, [], []).map((r) => r.model)));
  const models = props.filters.models.filter((m) => validModels.has(m));
  applyDownstream(families, models);
}
function onModelsChange(models: string[]) {
  applyDownstream(props.filters.families, models);
}
function onWorkcentersChange(workcenter_names: string[]) {
  const validEq = new Set(matchRows(props.filters.families, props.filters.models, workcenter_names).map((r) => r.equipment_id));
  const equipment_ids = props.filters.equipment_ids.filter((e) => validEq.has(e));
  emit('update:filters', { ...props.filters, workcenter_names, equipment_ids });
}
function onEquipmentChange(equipment_ids: string[]) {
  emit('update:filters', { ...props.filters, equipment_ids });
}
// Re-prune workcenters + equipment for a given (families, models).
function applyDownstream(families: string[], models: string[]) {
  const validWc = new Set(distinct(matchRows(families, models, []).map((r) => r.workcenter)));
  const workcenter_names = props.filters.workcenter_names.filter((w) => validWc.has(w));
  const validEq = new Set(matchRows(families, models, workcenter_names).map((r) => r.equipment_id));
  const equipment_ids = props.filters.equipment_ids.filter((e) => validEq.has(e));
  emit('update:filters', { ...props.filters, families, models, workcenter_names, equipment_ids });
}

function handleSubmit() {
  emit('submit');
}

function handleClear() {
  emit('update:filters', {
    ...props.filters,
    families: [],
    models: [],
    workcenter_names: [],
    packages: [],
    pj_types: [],
    equipment_ids: [],
  });
  emit('clear');
}

// UPH-only rule: date range is the sole required input (families empty = both).
const canSubmit = computed(() =>
  !props.loading.querying &&
  !!props.filters.date_from &&
  !!props.filters.date_to &&
  props.filters.date_from <= props.filters.date_to,
);

const equipmentPlaceholder = computed(() => {
  if (props.machineOptionsLoading) return '載入中...';
  const n = equipmentOptions.value.length;
  return n ? `全部機台 (${n} 台)` : '全部機台';
});
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

      <!-- DB/WB category (GDBA/GWBA) -->
      <div class="filter-group">
        <label class="filter-label">類別 (Die-Bond / Wire-Bond)</label>
        <MultiSelect
          :model-value="filters.families"
          :options="familyOptions"
          :disabled="loading.querying || machineOptionsLoading"
          placeholder="全部類別"
          data-testid="ctrl-family-select"
          @update:model-value="onFamiliesChange"
        />
      </div>

      <!-- 機型 (RESOURCEFAMILYNAME) — cascaded by category -->
      <div class="filter-group">
        <label class="filter-label">機型 / Model</label>
        <MultiSelect
          :model-value="filters.models"
          :options="modelOptions"
          :disabled="loading.querying || machineOptionsLoading"
          :placeholder="machineOptionsLoading ? '載入中...' : '全部機型'"
          searchable
          data-testid="ctrl-model-select"
          @update:model-value="onModelsChange"
        />
      </div>

      <!-- 工作站 (WORKCENTERNAME) — cascaded -->
      <div class="filter-group">
        <label class="filter-label">工作站 / Workcenter</label>
        <MultiSelect
          :model-value="filters.workcenter_names"
          :options="workcenterOptions"
          :disabled="loading.querying || machineOptionsLoading"
          :placeholder="machineOptionsLoading ? '載入中...' : '全部工作站'"
          searchable
          data-testid="ctrl-workcenter-select"
          @update:model-value="onWorkcentersChange"
        />
      </div>

      <!-- 機台 (RESOURCENAME / EQUIPMENT_ID) — cascaded, searchable (408) -->
      <div class="filter-group">
        <label class="filter-label">機台 ID / Equipment</label>
        <MultiSelect
          :model-value="filters.equipment_ids"
          :options="equipmentOptions"
          :disabled="loading.querying || machineOptionsLoading"
          :placeholder="equipmentPlaceholder"
          searchable
          data-testid="ctrl-equipment-select"
          @update:model-value="onEquipmentChange"
        />
      </div>

      <!-- Options-load warning (machine-options degrade) -->
      <div v-if="machineOptionsError" class="filter-group-full product-options-warning" data-testid="machine-options-warning" role="alert">
        機型 / 工作站 / 機台 選項載入失敗，可改用日期與 Package / Type 篩選：{{ machineOptionsError }}
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
          日期為必填；類別 / 機型 / 工作站 / 機台 皆為選填（留空代表全部），機型以下逐層連動。
        </div>
      </div>
    </div>
  </section>
</template>
