<script setup lang="ts">
import { computed } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import EmptyState from '../shared-ui/components/EmptyState.vue';
import DataTable from '../shared-ui/components/DataTable.vue';
import DataTableColumn from '../shared-ui/components/DataTableColumn.vue';

interface RankingItem {
  equipment_id: string;
  workcenter_name: string | null;
  db_wb_label: string | null;
  pj_type: string | null;
  avg_uph: number | null;
  sample_count: number;
}

const props = defineProps<{
  items?: RankingItem[];
  // Option source for this block's OWN independent Type filter. Sourced from
  // the already-loaded post-spool filter-options (pj_type_options) — NOT
  // from re-querying the ranking endpoint with an empty selection, since
  // interaction-design.md §Confirmed #2 requires the ranking endpoint to
  // stay un-queried until the engineer picks at least one Type.
  typeOptions?: string[];
  selectedTypes?: string[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:selectedTypes', value: string[]): void;
}>();

const hasSelection = computed(() => (props.selectedTypes?.length ?? 0) > 0);
const hasData = computed(() => hasSelection.value && Array.isArray(props.items) && (props.items?.length ?? 0) > 0);

function formatUph(value: number | null): string {
  if (value === null || value === undefined) return '—';
  return Number(value).toLocaleString('zh-TW', { maximumFractionDigits: 2 });
}
</script>

<template>
  <section class="card ui-card" data-testid="ranking-block">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">設備 UPH 排行（由低至高）</div>
      <div class="ranking-type-filter" data-testid="ranking-type-filter-wrap">
        <label class="filter-label ranking-type-filter-label">排行專屬 Type 篩選（與全域 Type 篩選各自獨立）</label>
        <MultiSelect
          :model-value="selectedTypes ?? []"
          :options="typeOptions ?? []"
          placeholder="請選擇 Type 以顯示排行"
          searchable
          data-testid="ctrl-ranking-type-filter"
          @update:model-value="(v: string[]) => emit('update:selectedTypes', v)"
        />
      </div>
    </div>
    <div class="card-body ui-card-body ranking-body">
      <EmptyState
        v-if="!hasSelection"
        type="filter-empty"
        message="請先選擇至少一個 Type，才會顯示排行"
        data-testid="ranking-prompt"
      />
      <template v-else>
        <div v-if="loading" class="ranking-loading">載入中...</div>
        <EmptyState v-else-if="!hasData" type="no-data" message="此範圍無 UPH 資料，請放寬日期或調整篩選器" data-testid="ranking-empty" />
        <DataTable v-else :data="items">
          <DataTableColumn column-key="equipment_id"    label="機台 ID"        :sortable="false" />
          <DataTableColumn column-key="workcenter_name"  label="工作站"        :sortable="false" />
          <DataTableColumn column-key="db_wb_label"      label="DB / WB"      :sortable="false" />
          <DataTableColumn column-key="pj_type"          label="Type"         :sortable="false" />
          <DataTableColumn column-key="avg_uph"          label="平均 UPH"     :sortable="false" />
          <DataTableColumn column-key="sample_count"     label="樣本數"        :sortable="false" />

          <template #cell="{ row, columnKey }">
            <template v-if="columnKey === 'workcenter_name'">
              {{ row.workcenter_name ?? '—' }}
            </template>
            <template v-else-if="columnKey === 'db_wb_label'">
              <!-- confirmed #7: only shown per-row when db_wb_label is non-null -->
              {{ row.db_wb_label ?? '—' }}
            </template>
            <template v-else-if="columnKey === 'pj_type'">
              {{ row.pj_type ?? '—' }}
            </template>
            <template v-else-if="columnKey === 'avg_uph'">
              {{ formatUph(row.avg_uph as number | null) }}
            </template>
          </template>
        </DataTable>
      </template>
    </div>
  </section>
</template>
