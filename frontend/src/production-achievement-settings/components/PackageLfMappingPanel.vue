<script setup lang="ts">
/**
 * PackageLfMappingPanel — D1 sparse exceptions-only PACKAGE_LF merge map
 * (business-rules.md PA-09, data-shape-contract.md §3.30). Absence falls
 * back to self (never excluded) — this panel edits ONLY the exception rows.
 *
 * Mirrors TargetEditPanel.vue's inline-edit shape + fail-closed editForbidden
 * pattern (production-achievement-overhaul, IP-9).
 */
import { computed, reactive, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { PackageLfMapRow } from '../composables/useProductionAchievementSettings';

interface Props {
  rows?: PackageLfMapRow[];
  unmappedHints?: string[];
  loading?: boolean;
  editForbidden?: boolean;
  editError?: string;
  editSaving?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  rows: () => [],
  unmappedHints: () => [],
  loading: false,
  editForbidden: false,
  editError: '',
  editSaving: false,
});

const emit = defineEmits<{
  save: [payload: { raw_package_lf: string; merged_group: string }];
  delete: [raw_package_lf: string];
}>();

const editingRaw = ref<string | null>(null);
const draftMergedGroup = ref('');

function startEdit(row: PackageLfMapRow): void {
  if (props.editForbidden) return;
  editingRaw.value = row.raw_package_lf;
  draftMergedGroup.value = row.merged_group;
}

function cancelEdit(): void {
  editingRaw.value = null;
  draftMergedGroup.value = '';
}

function confirmEdit(row: PackageLfMapRow): void {
  const merged = draftMergedGroup.value.trim();
  if (!merged) return;
  emit('save', { raw_package_lf: row.raw_package_lf, merged_group: merged });
  editingRaw.value = null;
}

function handleDelete(row: PackageLfMapRow): void {
  if (props.editForbidden) return;
  emit('delete', row.raw_package_lf);
}

// New-mapping form — free text for both fields (no OD-12 constraint on this
// panel; a newly-appeared raw PACKAGE_LF value is often not yet known anywhere).
const newRowOpen = ref(false);
const newRow = reactive({ raw_package_lf: '', merged_group: '' });
const newRowError = ref('');

function openNewRow(prefillRaw?: string): void {
  if (props.editForbidden) return;
  newRowOpen.value = true;
  newRow.raw_package_lf = prefillRaw || '';
  newRow.merged_group = '';
  newRowError.value = '';
}

function submitNewRow(): void {
  const raw = newRow.raw_package_lf.trim();
  const merged = newRow.merged_group.trim();
  if (!raw || !merged) {
    newRowError.value = '請填寫原始值與合併群組名稱';
    return;
  }
  emit('save', { raw_package_lf: raw, merged_group: merged });
  newRowOpen.value = false;
}

const isEmpty = computed(() => !props.loading && props.rows.length === 0);
</script>

<template>
  <div class="pa-settings-panel" data-testid="pa-settings-pkg-panel">
    <div class="pa-settings-panel__header">
      <h3 class="pa-settings-panel__title">PACKAGE_LF 合併對照</h3>
      <button
        v-if="!editForbidden"
        type="button"
        class="ui-btn ui-btn--secondary ui-btn--sm"
        data-testid="pa-pkg-new-btn"
        :disabled="editSaving"
        @click="openNewRow()"
      >
        新增合併規則
      </button>
    </div>

    <p v-if="editForbidden" class="pa-settings-panel__readonly-note" role="status" data-testid="pa-pkg-readonly-note">
      您目前為檢視模式，無法編輯 PACKAGE_LF 合併對照。
    </p>
    <p v-if="editError" class="pa-settings-panel__error" role="alert" data-testid="pa-pkg-edit-error">{{ editError }}</p>

    <div v-if="newRowOpen" class="pa-settings-panel__new-row" data-testid="pa-pkg-new-row">
      <input v-model="newRow.raw_package_lf" type="text" class="pa-settings-panel__input" placeholder="原始 PACKAGE_LF" data-testid="pa-pkg-new-raw" />
      <input v-model="newRow.merged_group" type="text" class="pa-settings-panel__input" placeholder="合併群組名稱" data-testid="pa-pkg-new-merged" />
      <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-pkg-new-save" @click="submitNewRow">儲存</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" @click="newRowOpen = false">取消</button>
      <span v-if="newRowError" class="pa-settings-panel__inline-error" role="alert">{{ newRowError }}</span>
    </div>

    <DataTable :data="(rows as unknown as Record<string, unknown>[])" :loading="loading" empty-type="no-data">
      <DataTableColumn column-key="raw_package_lf" label="原始值" />
      <DataTableColumn column-key="merged_group" label="合併群組" />
      <DataTableColumn column-key="updated_at" label="最後更新" />
      <DataTableColumn column-key="updated_by" label="更新人" />
      <DataTableColumn column-key="actions" label="操作" align="center" />
      <template #cell="{ columnKey, row }">
        <template v-if="columnKey === 'merged_group'">
          <span v-if="editingRaw !== (row as unknown as PackageLfMapRow).raw_package_lf">{{ (row as unknown as PackageLfMapRow).merged_group }}</span>
          <input
            v-else
            v-model="draftMergedGroup"
            type="text"
            class="pa-settings-panel__input pa-settings-panel__input--sm"
            data-testid="pa-pkg-edit-input"
            @keydown.enter="confirmEdit(row as unknown as PackageLfMapRow)"
            @keydown.escape="cancelEdit"
          />
        </template>
        <template v-else-if="columnKey === 'actions'">
          <template v-if="!editForbidden">
            <template v-if="editingRaw !== (row as unknown as PackageLfMapRow).raw_package_lf">
              <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-testid="pa-pkg-edit-btn" :disabled="editSaving" @click="startEdit(row as unknown as PackageLfMapRow)">編輯</button>
              <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-testid="pa-pkg-delete-btn" :disabled="editSaving" @click="handleDelete(row as unknown as PackageLfMapRow)">刪除</button>
            </template>
            <template v-else>
              <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-pkg-save-btn" :disabled="editSaving" @click="confirmEdit(row as unknown as PackageLfMapRow)">儲存</button>
              <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="editSaving" @click="cancelEdit">取消</button>
            </template>
          </template>
        </template>
        <template v-else>{{ (row as Record<string, unknown>)[columnKey] }}</template>
      </template>
    </DataTable>

    <p v-if="isEmpty" class="pa-settings-panel__empty-note">尚未設定任何合併規則（所有原始值皆各自成組）</p>

    <div v-if="unmappedHints.length" class="pa-settings-panel__hints" data-testid="pa-pkg-hints">
      <h4 class="pa-settings-panel__hints-title">近期出現、尚未設定合併規則的原始值</h4>
      <div class="pa-settings-panel__hint-list">
        <button
          v-for="hint in unmappedHints"
          :key="hint"
          type="button"
          class="pa-settings-panel__hint-chip"
          data-testid="pa-pkg-hint-item"
          :disabled="editForbidden"
          @click="openNewRow(hint)"
        >
          {{ hint }} +
        </button>
      </div>
    </div>
  </div>
</template>
