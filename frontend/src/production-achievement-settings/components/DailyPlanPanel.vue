<script setup lang="ts">
/**
 * DailyPlanPanel — production_achievement_daily_plans (business-rules.md
 * PA-11, data-shape-contract.md §3.32). Keyed (workcenter_group,
 * package_lf_group), no shift dimension — fully independent of the legacy
 * shift-keyed targets table (TargetEditPanel.vue, unchanged).
 *
 * OD-12: the new-row form's workcenter_group/package_lf_group are
 * CONSTRAINED DROPDOWNS only (sourced from workcenter-merge-map's merged
 * names and package-lf-map/known-values' resolved groups respectively) — no
 * free-text option, so a plan can never be created against a group that
 * cannot actually appear in the report.
 */
import { computed, reactive, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { DailyPlanRow } from '../composables/useProductionAchievementSettings';

interface Props {
  rows?: DailyPlanRow[];
  workcenterGroupOptions?: string[];
  packageLfGroupOptions?: string[];
  loading?: boolean;
  editForbidden?: boolean;
  editError?: string;
  editSaving?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  rows: () => [],
  workcenterGroupOptions: () => [],
  packageLfGroupOptions: () => [],
  loading: false,
  editForbidden: false,
  editError: '',
  editSaving: false,
});

const emit = defineEmits<{
  save: [payload: { workcenter_group: string; package_lf_group: string; daily_plan_qty: number }];
}>();

function keyFor(row: { workcenter_group: string; package_lf_group: string }): string {
  return `${row.workcenter_group}::${row.package_lf_group}`;
}

/** Mirrors utils.ts's validateTargetQtyInput() — non-negative integer only (data-shape-contract.md §3.32). */
function validateQtyInput(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed === '') return '每日計畫量為必填';
  if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return '每日計畫量必須為數字';
  const n = Number(trimmed);
  if (!Number.isFinite(n)) return '每日計畫量必須為數字';
  if (!Number.isInteger(n)) return '每日計畫量必須為整數';
  if (n < 0) return '每日計畫量不可為負數';
  return '';
}

const editingKey = ref<string | null>(null);
const draftQty = ref('');
const draftError = ref('');

function startEdit(row: DailyPlanRow): void {
  if (props.editForbidden) return;
  editingKey.value = keyFor(row);
  draftQty.value = String(row.daily_plan_qty ?? '');
  draftError.value = '';
}

function cancelEdit(): void {
  editingKey.value = null;
  draftQty.value = '';
  draftError.value = '';
}

function confirmEdit(row: DailyPlanRow): void {
  const message = validateQtyInput(draftQty.value);
  if (message) {
    draftError.value = message;
    return;
  }
  emit('save', { workcenter_group: row.workcenter_group, package_lf_group: row.package_lf_group, daily_plan_qty: Number(draftQty.value) });
  editingKey.value = null;
}

// New-row form — OD-12: workcenter_group/package_lf_group are constrained
// dropdowns only, no free-text escape.
const newRowOpen = ref(false);
const newRow = reactive({ workcenter_group: '', package_lf_group: '', daily_plan_qty: '' });
const newRowError = ref('');

function openNewRow(): void {
  if (props.editForbidden) return;
  newRowOpen.value = true;
  newRow.workcenter_group = '';
  newRow.package_lf_group = '';
  newRow.daily_plan_qty = '';
  newRowError.value = '';
}

function submitNewRow(): void {
  if (!newRow.workcenter_group || !newRow.package_lf_group) {
    newRowError.value = '請選擇站點群組與包裝群組';
    return;
  }
  const message = validateQtyInput(newRow.daily_plan_qty);
  if (message) {
    newRowError.value = message;
    return;
  }
  emit('save', {
    workcenter_group: newRow.workcenter_group,
    package_lf_group: newRow.package_lf_group,
    daily_plan_qty: Number(newRow.daily_plan_qty),
  });
  newRowOpen.value = false;
}

const isEmpty = computed(() => !props.loading && props.rows.length === 0);
</script>

<template>
  <div class="pa-settings-panel" data-testid="pa-settings-plan-panel">
    <div class="pa-settings-panel__header">
      <h3 class="pa-settings-panel__title">每日計畫量設定</h3>
      <button
        v-if="!editForbidden"
        type="button"
        class="ui-btn ui-btn--secondary ui-btn--sm"
        data-testid="pa-plan-new-btn"
        :disabled="editSaving"
        @click="openNewRow"
      >
        新增每日計畫
      </button>
    </div>

    <p v-if="editForbidden" class="pa-settings-panel__readonly-note" role="status" data-testid="pa-plan-readonly-note">
      您目前為檢視模式，無法編輯每日計畫量。
    </p>
    <p v-if="editError" class="pa-settings-panel__error" role="alert" data-testid="pa-plan-edit-error">{{ editError }}</p>

    <div v-if="newRowOpen" class="pa-settings-panel__new-row" data-testid="pa-plan-new-row">
      <select v-model="newRow.workcenter_group" class="pa-settings-panel__select" data-testid="pa-plan-new-workcenter">
        <option value="" disabled>站點群組</option>
        <option v-for="group in workcenterGroupOptions" :key="group" :value="group">{{ group }}</option>
      </select>
      <select v-model="newRow.package_lf_group" class="pa-settings-panel__select" data-testid="pa-plan-new-package">
        <option value="" disabled>包裝群組</option>
        <option v-for="group in packageLfGroupOptions" :key="group" :value="group">{{ group }}</option>
      </select>
      <input
        v-model="newRow.daily_plan_qty"
        type="text"
        inputmode="numeric"
        class="pa-settings-panel__input"
        placeholder="每日計畫量"
        data-testid="pa-plan-new-qty"
      />
      <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-plan-new-save" @click="submitNewRow">儲存</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" @click="newRowOpen = false">取消</button>
      <span v-if="newRowError" class="pa-settings-panel__inline-error" role="alert">{{ newRowError }}</span>
    </div>

    <DataTable :data="(rows as unknown as Record<string, unknown>[])" :loading="loading" empty-type="no-data">
      <DataTableColumn column-key="workcenter_group" label="站點群組" />
      <DataTableColumn column-key="package_lf_group" label="包裝群組" />
      <DataTableColumn column-key="daily_plan_qty" label="每日計畫量" align="right" />
      <DataTableColumn column-key="updated_at" label="最後更新" />
      <DataTableColumn column-key="updated_by" label="更新人" />
      <DataTableColumn column-key="actions" label="操作" align="center" />
      <template #cell="{ columnKey, row }">
        <template v-if="columnKey === 'daily_plan_qty'">
          <span v-if="editingKey !== keyFor(row as unknown as DailyPlanRow)">{{ (row as unknown as DailyPlanRow).daily_plan_qty }}</span>
          <span v-else class="pa-settings-panel__edit-cell">
            <input
              v-model="draftQty"
              type="text"
              inputmode="numeric"
              class="pa-settings-panel__input pa-settings-panel__input--sm"
              data-testid="pa-plan-edit-input"
              @keydown.enter="confirmEdit(row as unknown as DailyPlanRow)"
              @keydown.escape="cancelEdit"
            />
            <span v-if="draftError" class="pa-settings-panel__inline-error" role="alert">{{ draftError }}</span>
          </span>
        </template>
        <template v-else-if="columnKey === 'actions'">
          <template v-if="!editForbidden">
            <button
              v-if="editingKey !== keyFor(row as unknown as DailyPlanRow)"
              type="button"
              class="ui-btn ui-btn--ghost ui-btn--sm"
              data-testid="pa-plan-edit-btn"
              :disabled="editSaving"
              @click="startEdit(row as unknown as DailyPlanRow)"
            >
              編輯
            </button>
            <template v-else>
              <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-plan-save-btn" :disabled="editSaving" @click="confirmEdit(row as unknown as DailyPlanRow)">儲存</button>
              <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="editSaving" @click="cancelEdit">取消</button>
            </template>
          </template>
        </template>
        <template v-else>{{ (row as Record<string, unknown>)[columnKey] }}</template>
      </template>
    </DataTable>

    <p v-if="isEmpty" class="pa-settings-panel__empty-note">尚未設定任何每日計畫量</p>
  </div>
</template>
