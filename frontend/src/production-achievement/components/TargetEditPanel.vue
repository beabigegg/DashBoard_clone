<script setup lang="ts">
/**
 * TargetEditPanel — view + inline edit of target_qty per (shift_code, workcenter_group).
 *
 * GET .../targets is always visible (no permission gate, per api-contract.md
 * row 258). The edit control (input + save button) is shown to any
 * authenticated user optimistically — there is no contract-declared
 * "am I whitelisted" endpoint for non-admin users (only the admin-only
 * GET /admin/api/production-achievement/permissions exists). `editForbidden`
 * is flipped by the parent the first time a PUT 403s, which disables further
 * attempts for the rest of the session per design.md's fail-closed intent.
 */
import { computed, reactive, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import { formatQty, validateTargetQtyInput } from '../utils';
import type { ProductionAchievementTargetRow } from '../composables/useProductionAchievement';

interface Props {
  targets?: ProductionAchievementTargetRow[];
  loading?: boolean;
  editForbidden?: boolean;
  editError?: string;
  editSaving?: boolean;
  workcenterGroupOptions?: string[];
  shiftCodeOptions?: string[];
}

const props = withDefaults(defineProps<Props>(), {
  targets: () => [],
  loading: false,
  editForbidden: false,
  editError: '',
  editSaving: false,
  workcenterGroupOptions: () => [],
  shiftCodeOptions: () => ['N', 'D', 'A', 'B', 'C'],
});

const emit = defineEmits<{
  (e: 'save', payload: { shift_code: string; workcenter_group: string; target_qty: number }): void;
}>();

const editingKey = ref<string | null>(null);
const draftValue = ref('');
const draftError = ref('');

function keyFor(row: { shift_code: string; workcenter_group: string }): string {
  return `${row.shift_code}::${row.workcenter_group}`;
}

function startEdit(row: ProductionAchievementTargetRow): void {
  if (props.editForbidden) return;
  editingKey.value = keyFor(row);
  draftValue.value = String(row.target_qty ?? '');
  draftError.value = '';
}

function cancelEdit(): void {
  editingKey.value = null;
  draftValue.value = '';
  draftError.value = '';
}

function confirmEdit(row: ProductionAchievementTargetRow): void {
  const message = validateTargetQtyInput(draftValue.value);
  if (message) {
    draftError.value = message;
    return;
  }
  emit('save', {
    shift_code: row.shift_code,
    workcenter_group: row.workcenter_group,
    target_qty: Number(draftValue.value),
  });
  editingKey.value = null;
}

// New-target creation (shift_code/workcenter_group not yet in the target table).
const newTargetOpen = ref(false);
const newTarget = reactive({ shift_code: '', workcenter_group: '', target_qty: '' });
const newTargetError = ref('');

function openNewTarget(): void {
  if (props.editForbidden) return;
  newTargetOpen.value = true;
  newTarget.shift_code = '';
  newTarget.workcenter_group = '';
  newTarget.target_qty = '';
  newTargetError.value = '';
}

function submitNewTarget(): void {
  if (!newTarget.shift_code || !newTarget.workcenter_group) {
    newTargetError.value = '請選擇班別與站點群組';
    return;
  }
  const message = validateTargetQtyInput(newTarget.target_qty);
  if (message) {
    newTargetError.value = message;
    return;
  }
  emit('save', {
    shift_code: newTarget.shift_code,
    workcenter_group: newTarget.workcenter_group,
    target_qty: Number(newTarget.target_qty),
  });
  newTargetOpen.value = false;
}

const isEmpty = computed(() => !props.loading && (props.targets || []).length === 0);
</script>

<template>
  <div class="pa-target-panel" data-testid="pa-target-panel">
    <div class="pa-target-panel__header">
      <h3 class="pa-card-title">目標值設定</h3>
      <button
        v-if="!editForbidden"
        type="button"
        class="ui-btn ui-btn--secondary ui-btn--sm"
        data-testid="pa-target-new-btn"
        :disabled="editSaving"
        @click="openNewTarget"
      >
        新增目標值
      </button>
    </div>

    <p v-if="editForbidden" class="pa-target-panel__readonly-note" role="status" data-testid="pa-target-readonly-note">
      您目前為檢視模式，無法編輯目標值。
    </p>
    <p v-if="editError" class="pa-target-panel__error" role="alert" data-testid="pa-target-edit-error">
      {{ editError }}
    </p>

    <div v-if="newTargetOpen" class="pa-target-panel__new-row" data-testid="pa-target-new-row">
      <select v-model="newTarget.shift_code" class="pa-target-panel__select" data-testid="pa-target-new-shift">
        <option value="" disabled>班別</option>
        <option v-for="code in shiftCodeOptions" :key="code" :value="code">{{ code }}</option>
      </select>
      <select v-model="newTarget.workcenter_group" class="pa-target-panel__select" data-testid="pa-target-new-workcenter">
        <option value="" disabled>站點群組</option>
        <option v-for="group in workcenterGroupOptions" :key="group" :value="group">{{ group }}</option>
      </select>
      <input
        v-model="newTarget.target_qty"
        type="text"
        inputmode="numeric"
        class="pa-target-panel__input"
        placeholder="目標值"
        data-testid="pa-target-new-qty"
      />
      <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-target-new-save" @click="submitNewTarget">
        儲存
      </button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" @click="newTargetOpen = false">
        取消
      </button>
      <span v-if="newTargetError" class="pa-target-panel__inline-error" role="alert">{{ newTargetError }}</span>
    </div>

    <DataTable :data="(targets as unknown as Record<string, unknown>[])" :loading="loading" empty-type="no-data">
      <DataTableColumn column-key="shift_code" label="班別" />
      <DataTableColumn column-key="workcenter_group" label="站點群組" />
      <DataTableColumn column-key="target_qty" label="目標值" align="right" />
      <DataTableColumn column-key="updated_at" label="最後更新" />
      <DataTableColumn column-key="updated_by" label="更新人" />
      <DataTableColumn column-key="actions" label="操作" align="center" />
      <template #cell="{ columnKey, row }">
        <template v-if="columnKey === 'target_qty'">
          <span v-if="editingKey !== keyFor(row as ProductionAchievementTargetRow)">
            {{ formatQty((row as ProductionAchievementTargetRow).target_qty) }}
          </span>
          <span v-else class="pa-target-panel__edit-cell">
            <input
              v-model="draftValue"
              type="text"
              inputmode="numeric"
              class="pa-target-panel__input pa-target-panel__input--sm"
              data-testid="pa-target-edit-input"
              @keydown.enter="confirmEdit(row as ProductionAchievementTargetRow)"
              @keydown.escape="cancelEdit"
            />
            <span v-if="draftError" class="pa-target-panel__inline-error" role="alert">{{ draftError }}</span>
          </span>
        </template>
        <template v-else-if="columnKey === 'actions'">
          <template v-if="!editForbidden">
            <button
              v-if="editingKey !== keyFor(row as ProductionAchievementTargetRow)"
              type="button"
              class="ui-btn ui-btn--ghost ui-btn--sm"
              data-testid="pa-target-edit-btn"
              :disabled="editSaving"
              @click="startEdit(row as ProductionAchievementTargetRow)"
            >
              編輯
            </button>
            <template v-else>
              <button
                type="button"
                class="ui-btn ui-btn--primary ui-btn--sm"
                data-testid="pa-target-save-btn"
                :disabled="editSaving"
                @click="confirmEdit(row as ProductionAchievementTargetRow)"
              >
                儲存
              </button>
              <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="editSaving" @click="cancelEdit">
                取消
              </button>
            </template>
          </template>
        </template>
      </template>
    </DataTable>

    <p v-if="isEmpty" class="pa-target-panel__empty-note">尚未設定任何目標值</p>
  </div>
</template>
