<script setup>
import MultiSelect from '../../resource-shared/components/MultiSelect.vue';

defineProps({
  filters: { type: Object, required: true },
  options: { type: Object, required: true },
  loading: { type: Object, required: true },
  activeFilterChips: { type: Array, default: () => [] },
});

defineEmits(['apply', 'clear', 'export-csv', 'remove-chip', 'pareto-scope-toggle']);
</script>

<template>
  <section class="card">
    <div class="card-header">
      <div class="card-title">查詢條件</div>
    </div>
    <div class="card-body filter-panel">
      <div class="filter-group">
        <label class="filter-label" for="start-date">開始日期</label>
        <input id="start-date" v-model="filters.startDate" type="date" class="filter-input" />
      </div>
      <div class="filter-group">
        <label class="filter-label" for="end-date">結束日期</label>
        <input id="end-date" v-model="filters.endDate" type="date" class="filter-input" />
      </div>

      <div class="filter-group">
        <label class="filter-label">Package</label>
        <MultiSelect
          :model-value="filters.packages"
          :options="options.packages"
          placeholder="全部 Package"
          searchable
          @update:model-value="filters.packages = $event"
        />
      </div>

      <div class="filter-group">
        <label class="filter-label" for="reason">報廢原因</label>
        <select id="reason" v-model="filters.reason" class="filter-input">
          <option value="">全部原因</option>
          <option v-for="reason in options.reasons" :key="reason" :value="reason">
            {{ reason }}
          </option>
        </select>
      </div>

      <div class="filter-group filter-group-full">
        <label class="filter-label">WORKCENTER GROUP</label>
        <MultiSelect
          :model-value="filters.workcenterGroups"
          :options="options.workcenterGroups"
          placeholder="全部工作中心群組"
          searchable
          @update:model-value="filters.workcenterGroups = $event"
        />
      </div>

      <div class="filter-toolbar">
        <div class="checkbox-row">
          <label class="checkbox-pill">
            <input v-model="filters.includeExcludedScrap" type="checkbox" />
            納入不計良率報廢
          </label>
          <label class="checkbox-pill">
            <input v-model="filters.excludeMaterialScrap" type="checkbox" />
            排除原物料報廢
          </label>
          <label class="checkbox-pill">
            <input v-model="filters.excludePbDiode" type="checkbox" />
            排除 PB_Diode
          </label>
          <label class="checkbox-pill">
            <input
              :checked="filters.paretoTop80"
              type="checkbox"
              @change="$emit('pareto-scope-toggle', $event.target.checked)"
            />
            Pareto 僅顯示累計前 80%
          </label>
        </div>
        <div class="filter-actions">
          <button class="btn btn-primary" :disabled="loading.querying" @click="$emit('apply')">查詢</button>
          <button class="btn btn-secondary" :disabled="loading.querying" @click="$emit('clear')">清除條件</button>
          <button class="btn btn-light btn-export" :disabled="loading.querying" @click="$emit('export-csv')">匯出 CSV</button>
        </div>
      </div>
    </div>
    <div class="card-body active-filter-chip-row" v-if="activeFilterChips.length > 0">
      <div class="filter-label">套用中篩選</div>
      <div class="chip-list">
        <div v-for="chip in activeFilterChips" :key="chip.key" class="filter-chip">
          <span>{{ chip.label }}</span>
          <button
            v-if="chip.removable"
            type="button"
            class="chip-remove"
            @click="$emit('remove-chip', chip)"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
