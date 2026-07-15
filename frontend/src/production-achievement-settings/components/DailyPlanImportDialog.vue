<script setup lang="ts">
/**
 * DailyPlanImportDialog — Excel-import flow for DailyPlanPanel.vue
 * (business-rules.md PA-16): pick a PJMES052-生產達成率.xlsx file → preview
 * (parse-only, no write) → user confirms selected rows → bulk upsert.
 *
 * Dumb component (props in / events out), matches the panel-family
 * convention in this app. Never calls the API directly — App.vue owns
 * previewDailyPlanImport()/confirmDailyPlanImport() via the composable.
 *
 * Decision 6 (orphan-prevention): invalid_* rows are never selectable —
 * checkboxes are disabled and rendered unchecked regardless of user action.
 * Decision 8: "unchanged" rows are shown but NOT pre-selected.
 */
import { computed, reactive, ref, watch } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';
import type { DailyPlanImportPreview, DailyPlanImportRow } from '../composables/useProductionAchievementSettings';

interface Props {
  open?: boolean;
  preview?: DailyPlanImportPreview | null;
  previewLoading?: boolean;
  confirmSaving?: boolean;
  confirmResult?: { acknowledged: boolean; upserted: number } | null;
  editError?: string;
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  preview: null,
  previewLoading: false,
  confirmSaving: false,
  confirmResult: null,
  editError: '',
});

const emit = defineEmits<{
  close: [];
  'select-file': [file: File];
  confirm: [rows: { workcenter_group: string; package_lf_group: string; daily_plan_qty: number }[]];
}>();

const STATUS_LABELS: Record<string, string> = {
  new: '新增',
  update: '更新',
  unchanged: '未變更',
  invalid_workcenter: '無法匯入',
  invalid_package: '無法匯入',
  invalid_qty: '無法匯入',
};

const STATUS_CLASSES: Record<string, string> = {
  new: 'pa-plan-import__tag--new',
  update: 'pa-plan-import__tag--update',
  unchanged: 'pa-plan-import__tag--unchanged',
  invalid_workcenter: 'pa-plan-import__tag--invalid',
  invalid_package: 'pa-plan-import__tag--invalid',
  invalid_qty: 'pa-plan-import__tag--invalid',
};

function keyFor(row: { workcenter_group: string; package_lf_group: string }): string {
  return `${row.workcenter_group}::${row.package_lf_group}`;
}

const selected = reactive(new Set<string>());

watch(
  () => props.preview,
  (preview) => {
    selected.clear();
    if (!preview) return;
    for (const row of preview.rows) {
      if (row.importable && row.default_selected) selected.add(keyFor(row));
    }
  },
  { immediate: true },
);

function toggleRow(row: DailyPlanImportRow): void {
  if (!row.importable) return;
  const key = keyFor(row);
  if (selected.has(key)) selected.delete(key);
  else selected.add(key);
}

const importableRows = computed<DailyPlanImportRow[]>(() => props.preview?.rows.filter((r) => r.importable) ?? []);
const allSelected = computed(() => importableRows.value.length > 0 && importableRows.value.every((r) => selected.has(keyFor(r))));

function toggleSelectAll(): void {
  if (allSelected.value) {
    selected.clear();
    return;
  }
  for (const row of importableRows.value) selected.add(keyFor(row));
}

const fileInput = ref<HTMLInputElement | null>(null);

function handleFileChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) emit('select-file', file);
  input.value = '';
}

function handleConfirm(): void {
  if (!props.preview) return;
  const rows = props.preview.rows
    .filter((r) => r.importable && selected.has(keyFor(r)))
    .map((r) => ({
      workcenter_group: r.workcenter_group,
      package_lf_group: r.package_lf_group,
      daily_plan_qty: r.daily_plan_qty as number,
    }));
  emit('confirm', rows);
}

function handleClose(): void {
  selected.clear();
  emit('close');
}
</script>

<template>
  <div v-if="open" class="pa-plan-import__overlay" data-testid="pa-plan-import-dialog" role="dialog" aria-modal="true">
    <div class="pa-plan-import__panel">
      <div class="pa-plan-import__header">
        <h3 class="pa-settings-panel__title">匯入每日計畫量（PJMES052-生產達成率）</h3>
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-testid="pa-plan-import-close" @click="handleClose">✕</button>
      </div>

      <p v-if="editError" class="pa-settings-panel__error" role="alert" data-testid="pa-plan-import-error">{{ editError }}</p>

      <template v-if="!confirmResult">
        <div class="pa-plan-import__file-row">
          <input
            ref="fileInput"
            type="file"
            accept=".xlsx"
            class="pa-plan-import__file-input"
            data-testid="pa-plan-import-file"
            :disabled="previewLoading"
            @change="handleFileChange"
          />
          <span v-if="previewLoading" class="pa-settings-panel__muted" data-testid="pa-plan-import-loading">解析中…</span>
        </div>

        <template v-if="preview">
          <p class="pa-plan-import__summary" data-testid="pa-plan-import-summary">
            共 {{ preview.summary.total_parsed }} 筆：新增 {{ preview.summary.new }}、更新 {{ preview.summary.update }}、
            未變更 {{ preview.summary.unchanged }}、無法匯入 {{ preview.summary.invalid }}
          </p>

          <div class="pa-plan-import__toolbar">
            <button type="button" class="ui-btn ui-btn--secondary ui-btn--sm" data-testid="pa-plan-import-toggle-all" @click="toggleSelectAll">
              {{ allSelected ? '取消全選' : '全選' }}
            </button>
          </div>

          <DataTable :data="(preview.rows as unknown as Record<string, unknown>[])" empty-type="no-data">
            <DataTableColumn column-key="select" label="選取" align="center" />
            <DataTableColumn column-key="workcenter_group" label="站點群組" />
            <DataTableColumn column-key="package_lf_group" label="Package Group" />
            <DataTableColumn column-key="daily_plan_qty" label="每日計畫量（檔案）" align="right" />
            <DataTableColumn column-key="current_qty" label="目前值" align="right" />
            <DataTableColumn column-key="status" label="狀態" />
            <template #cell="{ columnKey, row }">
              <template v-if="columnKey === 'select'">
                <input
                  type="checkbox"
                  :data-testid="`pa-plan-import-row-select-${keyFor(row as unknown as DailyPlanImportRow)}`"
                  :disabled="!(row as unknown as DailyPlanImportRow).importable"
                  :checked="selected.has(keyFor(row as unknown as DailyPlanImportRow))"
                  @change="toggleRow(row as unknown as DailyPlanImportRow)"
                />
              </template>
              <template v-else-if="columnKey === 'current_qty'">
                {{ (row as unknown as DailyPlanImportRow).current_qty ?? '—' }}
              </template>
              <template v-else-if="columnKey === 'status'">
                <span class="pa-plan-import__tag" :class="STATUS_CLASSES[(row as unknown as DailyPlanImportRow).status]">
                  {{ STATUS_LABELS[(row as unknown as DailyPlanImportRow).status] }}
                </span>
                <span v-if="(row as unknown as DailyPlanImportRow).warning" class="pa-settings-panel__inline-error">
                  {{ (row as unknown as DailyPlanImportRow).warning }}
                </span>
              </template>
              <template v-else>{{ (row as Record<string, unknown>)[columnKey] }}</template>
            </template>
          </DataTable>

          <details v-if="preview.missing_from_file.length > 0" class="pa-plan-import__missing" data-testid="pa-plan-import-missing">
            <summary>以下 {{ preview.missing_from_file.length }} 筆不在檔案中，將維持原值不變</summary>
            <ul>
              <li v-for="row in preview.missing_from_file" :key="keyFor(row)">
                {{ row.workcenter_group }} / {{ row.package_lf_group }}（目前值 {{ row.daily_plan_qty }}）
              </li>
            </ul>
          </details>

          <div class="pa-plan-import__actions">
            <button
              type="button"
              class="ui-btn ui-btn--primary ui-btn--sm"
              data-testid="pa-plan-import-confirm"
              :disabled="selected.size === 0 || confirmSaving"
              @click="handleConfirm"
            >
              確認匯入（{{ selected.size }} 筆）
            </button>
            <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="confirmSaving" @click="handleClose">取消</button>
          </div>
        </template>
      </template>

      <template v-else>
        <p class="pa-plan-import__result" role="status" data-testid="pa-plan-import-result">已匯入 {{ confirmResult.upserted }} 筆</p>
        <div class="pa-plan-import__actions">
          <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-testid="pa-plan-import-done" @click="handleClose">關閉</button>
        </div>
      </template>
    </div>
  </div>
</template>
