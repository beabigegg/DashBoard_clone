<script setup>
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

import EquipmentJobsPanel from './EquipmentJobsPanel.vue';
import EquipmentLotsTable from './EquipmentLotsTable.vue';
import EquipmentRejectsTable from './EquipmentRejectsTable.vue';
import LotTimeline from './LotTimeline.vue';

const props = defineProps({
  inputType: {
    type: String,
    default: 'lot_id',
  },
  inputTypeOptions: {
    type: Array,
    default: () => [],
  },
  inputText: {
    type: String,
    default: '',
  },
  parsedInputCount: {
    type: Number,
    default: 0,
  },
  workcenterGroupOptions: {
    type: Array,
    default: () => [],
  },
  selectedWorkcenterGroups: {
    type: Array,
    default: () => [],
  },
  resolvedEquipmentIds: {
    type: Array,
    default: () => [],
  },
  resolvedEquipmentNames: {
    type: Array,
    default: () => [],
  },
  lookupMessage: {
    type: String,
    default: '',
  },
  traceEntries: {
    type: Array,
    default: () => [],
  },
  startDate: {
    type: String,
    default: '',
  },
  endDate: {
    type: String,
    default: '',
  },
  activeSubTab: {
    type: String,
    default: 'lots',
  },
  loading: {
    type: Object,
    required: true,
  },
  errors: {
    type: Object,
    required: true,
  },
  lotsRows: {
    type: Array,
    default: () => [],
  },
  lotsPagination: {
    type: Object,
    default: () => ({ page: 1, per_page: 0, total: 0, total_pages: 1 }),
  },
  jobsRows: {
    type: Array,
    default: () => [],
  },
  rejectsRows: {
    type: Array,
    default: () => [],
  },
  exporting: {
    type: Object,
    required: true,
  },
  canExportSubTab: {
    type: Function,
    required: true,
  },
  pageSizeOptions: {
    type: Array,
    default: () => [25, 50, 100, 200],
  },
});

const emit = defineEmits([
  'update:input-type',
  'update:input-text',
  'update:selected-workcenter-groups',
  'lookup',
  'change-sub-tab',
  'change-lots-page',
  'change-lots-page-size',
  'export-sub-tab',
]);

const tabMeta = Object.freeze({
  lots: '生產紀錄',
  jobs: '維修紀錄',
  rejects: '報廢紀錄',
});

const subTabs = Object.keys(tabMeta);

const MAX_INPUT = 100;

function inputPlaceholder() {
  return props.inputType === 'work_order'
    ? '輸入工單號，每行一筆或以逗號分隔'
    : '輸入 LOT ID，每行一筆或以逗號分隔';
}
</script>

<template>
  <div class="space-y-3">
    <!-- Input card -->
    <section class="card ui-card">
      <div class="card-body ui-card-body">
        <div class="le-filter-panel">
          <!-- Row 1: workcenter group + input type -->
          <div class="le-filter-row">
            <label class="filter-group le-wc-group">
              <span class="filter-label">站點群組（可複選）</span>
              <MultiSelect
                :model-value="selectedWorkcenterGroups"
                :options="workcenterGroupOptions"
                :disabled="loading.bootstrapping"
                searchable
                placeholder="請選擇站點群組"
                @update:model-value="emit('update:selected-workcenter-groups', $event)"
              />
            </label>

            <label class="filter-group">
              <span class="filter-label">查詢類型</span>
              <select
                class="query-tool-select"
                :value="inputType"
                @change="emit('update:input-type', $event.target.value)"
              >
                <option
                  v-for="opt in inputTypeOptions"
                  :key="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </option>
              </select>
            </label>
          </div>

          <!-- Row 2: textarea + button -->
          <div class="le-input-row">
            <label class="filter-group le-input-group">
              <span class="filter-label">
                {{ inputType === 'work_order' ? '工單' : 'LOT ID' }}（逗號或換行分隔）
              </span>
              <textarea
                class="query-tool-textarea"
                rows="3"
                :value="inputText"
                :placeholder="inputPlaceholder()"
                @input="emit('update:input-text', $event.target.value)"
              />
              <span class="query-tool-muted le-input-count">
                已輸入 {{ parsedInputCount }} / {{ MAX_INPUT }}
              </span>
            </label>

            <div class="le-action">
              <button
                type="button"
                class="ui-btn ui-btn--primary"
                :disabled="loading.lookup || parsedInputCount === 0 || selectedWorkcenterGroups.length === 0"
                @click="emit('lookup')"
              >
                {{ loading.lookup ? '查詢中...' : '查詢' }}
              </button>
            </div>
          </div>
        </div>

        <ErrorBanner :message="errors.lookup" />

        <!-- Lookup result message -->
        <p
          v-if="lookupMessage && !errors.lookup"
          class="le-lookup-message"
          :class="{ 'le-lookup-empty': resolvedEquipmentIds.length === 0 }"
        >
          {{ lookupMessage }}
          <template v-if="startDate && endDate">
            （資料區間 {{ startDate }} ~ {{ endDate }}）
          </template>
        </p>

        <!-- Trace map: show which lots were traced to parent -->
        <div v-if="traceEntries.length > 0" class="le-trace-panel">
          <p class="le-trace-title">以下批次在指定站點無紀錄，已自動追溯至母批：</p>
          <div class="le-trace-list">
            <span v-for="entry in traceEntries" :key="entry.from" class="le-trace-item">
              {{ entry.from }} → {{ entry.to }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <!-- Results card (only show after successful lookup) -->
    <section v-if="resolvedEquipmentIds.length > 0" class="card ui-card">
      <div class="card-body ui-card-body">
        <div class="query-tool-sub-tab-bar">
          <button
            v-for="tab in subTabs"
            :key="tab"
            type="button"
            class="query-tool-sub-tab"
            :class="{ active: tab === activeSubTab }"
            @click="emit('change-sub-tab', tab)"
          >
            {{ tabMeta[tab] }}
          </button>
        </div>

        <EquipmentLotsTable
          v-if="activeSubTab === 'lots'"
          :rows="lotsRows"
          :loading="loading.lots"
          :error="errors.lots"
          :export-disabled="!canExportSubTab('lots')"
          :exporting="exporting.lots"
          @export="emit('export-sub-tab', 'lots')"
        />
        <div
          v-if="activeSubTab === 'lots' && (lotsPagination?.total || 0) > 0"
          class="query-tool-pagination"
        >
          <span class="query-tool-muted">
            第 {{ lotsPagination.page }} / {{ lotsPagination.total_pages }} 頁，共
            {{ lotsPagination.total }} 筆
          </span>
          <label class="query-tool-page-size">
            每頁
            <select
              :value="lotsPagination.per_page"
              @change="emit('change-lots-page-size', Number($event.target.value))"
            >
              <option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
            </select>
            筆
          </label>
          <div class="query-tool-pagination-actions">
            <button
              type="button"
              class="ui-btn ui-btn--ghost"
              :disabled="loading.lots || lotsPagination.page <= 1"
              @click="emit('change-lots-page', lotsPagination.page - 1)"
            >
              上一頁
            </button>
            <button
              type="button"
              class="ui-btn ui-btn--ghost"
              :disabled="loading.lots || lotsPagination.page >= lotsPagination.total_pages"
              @click="emit('change-lots-page', lotsPagination.page + 1)"
            >
              下一頁
            </button>
          </div>
        </div>
        <LotTimeline
          v-if="activeSubTab === 'lots' && lotsRows.length > 0"
          :history-rows="lotsRows"
        />

        <EquipmentJobsPanel
          v-if="activeSubTab === 'jobs'"
          :rows="jobsRows"
          :loading="loading.jobs"
          :error="errors.jobs"
          :export-disabled="!canExportSubTab('jobs')"
          :exporting="exporting.jobs"
          @export="emit('export-sub-tab', 'jobs')"
        />

        <EquipmentRejectsTable
          v-if="activeSubTab === 'rejects'"
          :rows="rejectsRows"
          :loading="loading.rejects"
          :error="errors.rejects"
          :export-disabled="!canExportSubTab('rejects')"
          :exporting="exporting.rejects"
          @export="emit('export-sub-tab', 'rejects')"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.le-filter-panel {
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p10');
  padding: theme('spacing.block');
  border-radius: theme('borderRadius.card');
  border: 1px solid theme('colors.stroke.soft');
  background: theme('colors.surface.muted');
}

.le-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: theme('spacing.2');
  align-items: flex-end;
}

.le-input-row {
  display: flex;
  gap: theme('spacing.2');
  align-items: flex-end;
}

.le-input-group {
  flex: 1;
  min-width: 0;
}

.le-action {
  flex-shrink: 0;
  padding-bottom: 2px;
}

.le-input-count {
  font-size: 11px;
  text-align: right;
  margin-top: 2px;
}

.le-lookup-message {
  margin-top: theme('spacing.token.p8');
  font-size: 13px;
  color: theme('colors.brand.600');
  font-weight: 500;
}

.le-lookup-empty {
  color: theme('colors.token.hf59e0b');
}

.le-trace-panel {
  margin-top: theme('spacing.token.p8');
  padding: theme('spacing.token.p8') theme('spacing.token.p10');
  background: theme('colors.token.hfefce8');
  border: 1px solid theme('colors.token.hfde68a');
  border-radius: 8px;
  font-size: 13px;
}

.le-trace-title {
  margin: 0 0 6px;
  font-weight: 500;
  color: theme('colors.token.h92400e');
}

.le-trace-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.le-trace-item {
  font-family: monospace;
  font-size: 12px;
  color: theme('colors.token.h92400e');
}
</style>
