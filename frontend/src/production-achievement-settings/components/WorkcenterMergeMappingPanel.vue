<script setup lang="ts">
/**
 * WorkcenterMergeMappingPanel — D2 explicit-inclusion workcenter merge map
 * (business-rules.md PA-10, data-shape-contract.md §3.31). Absence EXCLUDES
 * the raw group from the report entirely — the OPPOSITE default from
 * PackageLfMappingPanel (D1). Never share join-kind assumptions across panels.
 *
 * OD-8: enumerates the FULL raw WORK_CENTER_GROUP universe (via
 * GET /known-workcenter-groups, cross-referenced against the ~12
 * currently-included rows) so an admin can switch a currently-excluded raw
 * group on, not just edit the ones already included.
 */
import { computed, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { WorkcenterFullListRow } from '../composables/useProductionAchievementSettings';

interface Props {
  fullList?: WorkcenterFullListRow[];
  loading?: boolean;
  editForbidden?: boolean;
  editError?: string;
  editSaving?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  fullList: () => [],
  loading: false,
  editForbidden: false,
  editError: '',
  editSaving: false,
});

const emit = defineEmits<{
  include: [payload: { raw_workcenter_group: string; merged_workcenter_group: string }];
  exclude: [raw_workcenter_group: string];
  rename: [payload: { raw_workcenter_group: string; merged_workcenter_group: string }];
}>();

const editingRaw = ref<string | null>(null);
const draftMergedName = ref('');

function toggleInclude(row: WorkcenterFullListRow): void {
  if (props.editForbidden) return;
  if (row.included) {
    emit('exclude', row.raw_workcenter_group);
  } else {
    // Including a previously-excluded raw group defaults its merged name to
    // itself (1:1) — the admin can rename it afterwards via the same inline edit.
    emit('include', { raw_workcenter_group: row.raw_workcenter_group, merged_workcenter_group: row.raw_workcenter_group });
  }
}

function startRename(row: WorkcenterFullListRow): void {
  if (props.editForbidden || !row.included) return;
  editingRaw.value = row.raw_workcenter_group;
  draftMergedName.value = row.merged_workcenter_group || row.raw_workcenter_group;
}

function cancelRename(): void {
  editingRaw.value = null;
  draftMergedName.value = '';
}

function confirmRename(row: WorkcenterFullListRow): void {
  const merged = draftMergedName.value.trim();
  if (!merged) return;
  emit('rename', { raw_workcenter_group: row.raw_workcenter_group, merged_workcenter_group: merged });
  editingRaw.value = null;
}

const isEmpty = computed(() => !props.loading && props.fullList.length === 0);
</script>

<template>
  <div class="pa-settings-panel" data-testid="pa-settings-wc-panel">
    <div class="pa-settings-panel__header">
      <h3 class="pa-settings-panel__title">站點群組合併對照（含未納入項目）</h3>
    </div>

    <p v-if="editForbidden" class="pa-settings-panel__readonly-note" role="status" data-testid="pa-wc-readonly-note">
      您目前為檢視模式，無法編輯站點群組合併對照。
    </p>
    <p v-if="editError" class="pa-settings-panel__error" role="alert" data-testid="pa-wc-edit-error">{{ editError }}</p>

    <DataTable :data="(fullList as unknown as Record<string, unknown>[])" :loading="loading" empty-type="no-data">
      <DataTableColumn column-key="raw_workcenter_group" label="原始站點群組" />
      <DataTableColumn column-key="included" label="納入報表" align="center" />
      <DataTableColumn column-key="merged_workcenter_group" label="合併名稱" />
      <DataTableColumn column-key="actions" label="操作" align="center" />
      <template #cell="{ columnKey, row }">
        <template v-if="columnKey === 'included'">
          <button
            type="button"
            class="pa-settings-panel__toggle"
            :class="(row as unknown as WorkcenterFullListRow).included ? 'pa-settings-panel__toggle--on' : 'pa-settings-panel__toggle--off'"
            :aria-pressed="(row as unknown as WorkcenterFullListRow).included"
            :disabled="editForbidden || editSaving"
            data-testid="pa-wc-toggle"
            @click="toggleInclude(row as unknown as WorkcenterFullListRow)"
          >
            {{ (row as unknown as WorkcenterFullListRow).included ? '已納入' : '未納入' }}
          </button>
        </template>
        <template v-else-if="columnKey === 'merged_workcenter_group'">
          <span v-if="!(row as unknown as WorkcenterFullListRow).included" class="pa-settings-panel__muted">—</span>
          <span v-else-if="editingRaw !== (row as unknown as WorkcenterFullListRow).raw_workcenter_group">{{ (row as unknown as WorkcenterFullListRow).merged_workcenter_group }}</span>
          <input
            v-else
            v-model="draftMergedName"
            type="text"
            class="pa-settings-panel__input pa-settings-panel__input--sm"
            data-testid="pa-wc-name-input"
            @keydown.enter="confirmRename(row as unknown as WorkcenterFullListRow)"
            @keydown.escape="cancelRename"
          />
        </template>
        <template v-else-if="columnKey === 'actions'">
          <template v-if="!editForbidden && (row as unknown as WorkcenterFullListRow).included">
            <button
              v-if="editingRaw !== (row as unknown as WorkcenterFullListRow).raw_workcenter_group"
              type="button"
              class="ui-btn ui-btn--ghost ui-btn--sm"
              data-testid="pa-wc-rename-btn"
              :disabled="editSaving"
              @click="startRename(row as unknown as WorkcenterFullListRow)"
            >
              重新命名
            </button>
            <template v-else>
              <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-wc-rename-save" :disabled="editSaving" @click="confirmRename(row as unknown as WorkcenterFullListRow)">儲存</button>
              <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="editSaving" @click="cancelRename">取消</button>
            </template>
          </template>
        </template>
        <template v-else>{{ (row as Record<string, unknown>)[columnKey] }}</template>
      </template>
    </DataTable>

    <p v-if="isEmpty" class="pa-settings-panel__empty-note">尚無站點群組資料</p>
  </div>
</template>
