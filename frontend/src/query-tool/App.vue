<script setup>
import { computed, onMounted } from 'vue';

import MultiSelect from '../resource-shared/components/MultiSelect.vue';
import FilterToolbar from '../shared-ui/components/FilterToolbar.vue';
import SectionCard from '../shared-ui/components/SectionCard.vue';
import { useQueryToolData } from './composables/useQueryToolData.js';

const {
  loading,
  errorMessage,
  successMessage,
  batch,
  equipment,
  resolvedColumns,
  historyColumns,
  associationColumns,
  equipmentColumns,
  hydrateFromUrl,
  resetEquipmentDateRange,
  bootstrap,
  resolveLots,
  loadLotHistory,
  loadAssociations,
  queryEquipmentPeriod,
  exportCurrentCsv,
} = useQueryToolData();

const equipmentOptions = computed(() =>
  equipment.options.map((item) => ({
    value: item.RESOURCEID,
    label: item.RESOURCENAME || item.RESOURCEID,
  })),
);

const workcenterGroupOptions = computed(() =>
  batch.workcenterGroups.map((group) => ({
    value: group.name || group,
    label: group.name || group,
  })),
);

function formatCell(value) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return String(value);
}

onMounted(async () => {
  hydrateFromUrl();
  if (!equipment.startDate || !equipment.endDate) {
    resetEquipmentDateRange();
  }
  await bootstrap();
});
</script>

<template>
  <div class="query-tool-page u-content-shell">
    <header class="query-tool-header">
      <h1>批次追蹤工具</h1>
    </header>

    <div class="u-panel-stack">
      <SectionCard>
        <template #header>
          <strong>Batch Query：LOT / Serial / Work Order 解析</strong>
        </template>

        <FilterToolbar>
          <label class="query-tool-filter">
            <span>查詢類型</span>
            <select v-model="batch.inputType">
              <option value="lot_id">LOT ID</option>
              <option value="serial_number">流水號</option>
              <option value="work_order">工單</option>
            </select>
          </label>
          <label class="query-tool-filter">
            <span>站點群組</span>
            <MultiSelect
              :model-value="batch.selectedWorkcenterGroups"
              :options="workcenterGroupOptions"
              :disabled="loading.bootstrapping"
              placeholder="全部群組"
              searchable
              @update:model-value="batch.selectedWorkcenterGroups = $event"
            />
          </label>
          <template #actions>
            <button type="button" class="query-tool-btn query-tool-btn-primary" :disabled="loading.resolving" @click="resolveLots">
              {{ loading.resolving ? '解析中...' : '解析' }}
            </button>
          </template>
        </FilterToolbar>

        <textarea
          v-model="batch.inputText"
          class="query-tool-textarea"
          placeholder="輸入查詢值（可換行或逗號分隔）"
        />

        <div v-if="batch.resolvedLots.length > 0" class="query-tool-table-wrap">
          <table class="query-tool-table">
            <thead>
              <tr>
                <th>操作</th>
                <th v-for="column in resolvedColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, index) in batch.resolvedLots"
                :key="row.container_id || row.CONTAINERID || index"
                :class="{ selected: batch.selectedContainerId === (row.container_id || row.CONTAINERID) }"
              >
                <td>
                  <button
                    type="button"
                    class="query-tool-btn query-tool-btn-ghost"
                    @click="loadLotHistory(row.container_id || row.CONTAINERID)"
                  >
                    載入歷程
                  </button>
                </td>
                <td v-for="column in resolvedColumns" :key="column">{{ formatCell(row[column]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard v-if="batch.selectedContainerId">
        <template #header>
          <strong>LOT 歷程：{{ batch.selectedContainerId }}</strong>
        </template>

        <div v-if="loading.history" class="query-tool-empty">載入歷程中...</div>
        <div v-else-if="batch.lotHistoryRows.length === 0" class="query-tool-empty">無 LOT 歷程資料</div>
        <div v-else class="query-tool-table-wrap">
          <table class="query-tool-table">
            <thead>
              <tr>
                <th v-for="column in historyColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in batch.lotHistoryRows" :key="row.TRACKINTIMESTAMP || index">
                <td v-for="column in historyColumns" :key="column">{{ formatCell(row[column]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <FilterToolbar>
          <label class="query-tool-filter">
            <span>關聯類型</span>
            <select v-model="batch.associationType">
              <option value="materials">materials</option>
              <option value="rejects">rejects</option>
              <option value="holds">holds</option>
              <option value="splits">splits</option>
              <option value="jobs">jobs</option>
            </select>
          </label>
          <template #actions>
            <button type="button" class="query-tool-btn query-tool-btn-primary" :disabled="loading.association" @click="loadAssociations">
              {{ loading.association ? '讀取中...' : '查詢關聯' }}
            </button>
          </template>
        </FilterToolbar>

        <div v-if="batch.associationRows.length > 0" class="query-tool-table-wrap">
          <table class="query-tool-table">
            <thead>
              <tr>
                <th v-for="column in associationColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in batch.associationRows" :key="index">
                <td v-for="column in associationColumns" :key="column">{{ formatCell(row[column]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>

      <SectionCard>
        <template #header>
          <strong>Equipment Period Query</strong>
        </template>

        <FilterToolbar>
          <label class="query-tool-filter">
            <span>設備（複選）</span>
            <MultiSelect
              :model-value="equipment.selectedEquipmentIds"
              :options="equipmentOptions"
              :disabled="loading.bootstrapping || loading.equipment"
              placeholder="全部設備"
              searchable
              @update:model-value="equipment.selectedEquipmentIds = $event"
            />
          </label>
          <label class="query-tool-filter">
            <span>查詢類型</span>
            <select v-model="equipment.equipmentQueryType">
              <option value="status_hours">status_hours</option>
              <option value="lots">lots</option>
              <option value="materials">materials</option>
              <option value="rejects">rejects</option>
              <option value="jobs">jobs</option>
            </select>
          </label>
          <label class="query-tool-filter">
            <span>開始</span>
            <input v-model="equipment.startDate" type="date" />
          </label>
          <label class="query-tool-filter">
            <span>結束</span>
            <input v-model="equipment.endDate" type="date" />
          </label>

          <template #actions>
            <button type="button" class="query-tool-btn query-tool-btn-primary" :disabled="loading.equipment" @click="queryEquipmentPeriod">
              {{ loading.equipment ? '查詢中...' : '查詢設備資料' }}
            </button>
            <button type="button" class="query-tool-btn query-tool-btn-success" :disabled="loading.exporting" @click="exportCurrentCsv">
              {{ loading.exporting ? '匯出中...' : '匯出 CSV' }}
            </button>
          </template>
        </FilterToolbar>

        <div v-if="equipment.rows.length > 0" class="query-tool-table-wrap">
          <table class="query-tool-table">
            <thead>
              <tr>
                <th v-for="column in equipmentColumns" :key="column">{{ column }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, index) in equipment.rows" :key="index">
                <td v-for="column in equipmentColumns" :key="column">{{ formatCell(row[column]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>

      <p v-if="loading.bootstrapping" class="query-tool-empty">初始化中...</p>
      <p v-if="errorMessage" class="query-tool-error">{{ errorMessage }}</p>
      <p v-if="successMessage" class="query-tool-success">{{ successMessage }}</p>
    </div>
  </div>
</template>
