<script setup lang="ts">
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';
import type { MachineOption } from '../../core/resource-history-filters';

interface GranularityItem {
  key: string;
  label: string;
}

interface FilterOptions {
  workcenterGroups: (string | number | Record<string, unknown>)[];
  families: (string | number | Record<string, unknown>)[];
  packageGroups: (string | number | Record<string, unknown>)[];
}


const GRANULARITY_ITEMS: GranularityItem[] = [
  { key: 'day', label: '日' },
  { key: 'week', label: '週' },
  { key: 'month', label: '月' },
  { key: 'year', label: '年' },
];

const props = withDefaults(defineProps<{
  filters: Record<string, unknown>;
  options?: FilterOptions;
  machineOptions?: MachineOption[];
  loading?: boolean;
}>(), {
  options: () => ({
    workcenterGroups: [],
    families: [],
    packageGroups: [],
  }),
  machineOptions: () => [],
  loading: false,
});

const emit = defineEmits<{
  'update-filters': [filters: Record<string, unknown>];
  'query': [];
  'clear': [];
}>();

function updateFilters(patch: Record<string, unknown>): void {
  emit('update-filters', {
    ...props.filters,
    ...patch,
  });
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner filter-rows">
      <!-- Row 1: 日期區間 & 粒度 -->
      <div class="filter-row">
        <div class="filter-field">
          <label for="history-start-date">開始</label>
          <input
            id="history-start-date"
            type="date"
            :value="(filters.startDate as string)"
            :disabled="loading"
            @input="updateFilters({ startDate: ($event.target as HTMLInputElement).value })"
          />
        </div>

        <div class="filter-field">
          <label for="history-end-date">結束</label>
          <input
            id="history-end-date"
            type="date"
            :value="(filters.endDate as string)"
            :disabled="loading"
            @input="updateFilters({ endDate: ($event.target as HTMLInputElement).value })"
          />
        </div>

        <div class="filter-field">
          <label>粒度</label>
          <div class="granularity-btns">
            <button
              v-for="item in GRANULARITY_ITEMS"
              :key="item.key"
              type="button"
              class="granularity-btn"
              :class="{ active: filters.granularity === item.key }"
              :disabled="loading"
              @click="updateFilters({ granularity: item.key })"
            >
              {{ item.label }}
            </button>
          </div>
        </div>
      </div>

      <!-- Row 2: 工站群組 & 型號 & 機台 & 封裝群組 -->
      <div class="filter-row">
        <div class="filter-field">
          <label>工站群組</label>
          <MultiSelect
            :model-value="(filters.workcenterGroups as string[])"
            :options="options.workcenterGroups"
            :disabled="loading"
            placeholder="全部站點"
            @update:model-value="updateFilters({ workcenterGroups: $event })"
          />
        </div>

        <div class="filter-field">
          <label>型號</label>
          <MultiSelect
            :model-value="(filters.families as string[])"
            :options="options.families"
            :disabled="loading"
            placeholder="全部型號"
            @update:model-value="updateFilters({ families: $event })"
          />
        </div>

        <div class="filter-field">
          <label>機台</label>
          <MultiSelect
            :model-value="(filters.machines as string[])"
            :options="(machineOptions as unknown as (string | number | Record<string, unknown>)[])"
            :disabled="loading"
            placeholder="全部機台"
            searchable
            @update:model-value="updateFilters({ machines: $event })"
          />
        </div>

        <div class="filter-field">
          <label>封裝群組</label>
          <MultiSelect
            :model-value="(filters.packageGroups as string[])"
            :options="options.packageGroups"
            :disabled="loading"
            placeholder="全部封裝群組"
            @update:model-value="updateFilters({ packageGroups: $event })"
          />
        </div>
      </div>

      <!-- Row 3: 生產設備 & 重點設備 & 監控設備 + 按鈕 -->
      <div class="filter-row">
        <div class="checkbox-row">
          <label class="checkbox-pill">
            <input
              type="checkbox"
              :checked="(filters.isProduction as boolean)"
              :disabled="loading"
              @change="updateFilters({ isProduction: ($event.target as HTMLInputElement).checked })"
            />
            生產設備
          </label>
          <label class="checkbox-pill">
            <input
              type="checkbox"
              :checked="(filters.isKey as boolean)"
              :disabled="loading"
              @change="updateFilters({ isKey: ($event.target as HTMLInputElement).checked })"
            />
            重點設備
          </label>
          <label class="checkbox-pill">
            <input
              type="checkbox"
              :checked="(filters.isMonitor as boolean)"
              :disabled="loading"
              @change="updateFilters({ isMonitor: ($event.target as HTMLInputElement).checked })"
            />
            監控設備
          </label>
        </div>

        <button type="button" class="ui-btn ui-btn--primary" :disabled="loading" @click="$emit('query')">查詢</button>
        <button type="button" class="ui-btn ui-btn--ghost" :disabled="loading" @click="$emit('clear')">清除條件</button>
      </div>
    </div>
  </section>
</template>
