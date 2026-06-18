<script setup lang="ts">
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface CoarseFilter {
  date_from: string;
  date_to: string;
  eqp_types: string[];
}

interface LoadingState {
  querying?: boolean;
  [key: string]: unknown;
}

const props = defineProps<{
  filters: CoarseFilter;
  eqpTypeOptions: string[];
  loading: LoadingState;
}>();

const emit = defineEmits<{
  (e: 'submit'): void;
  (e: 'clear'): void;
}>();
</script>

<template>
  <section class="card ui-card filter-query-card">
    <div class="card-header ui-card-header">
      <div class="card-title ui-card-title">查詢條件</div>
    </div>
    <div class="card-body ui-card-body filter-panel">
      <div class="filter-group">
        <label class="filter-label" for="eap-date-from">開始日期 <span class="filter-required">*</span></label>
        <input
          id="eap-date-from"
          v-model="filters.date_from"
          type="date"
          class="filter-input"
          required
        />
      </div>

      <div class="filter-group">
        <label class="filter-label" for="eap-date-to">結束日期 <span class="filter-required">*</span></label>
        <input
          id="eap-date-to"
          v-model="filters.date_to"
          type="date"
          class="filter-input"
          required
        />
      </div>

      <div class="filter-group filter-group-wide">
        <label class="filter-label">EQP 機台類型 <span class="filter-required">*</span></label>
        <MultiSelect
          :model-value="filters.eqp_types"
          :options="eqpTypeOptions"
          placeholder="請選擇機台類型（必填）"
          searchable
          @update:model-value="filters.eqp_types = $event"
        />
      </div>

      <div class="filter-toolbar filter-group-full">
        <div class="filter-actions">
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            :disabled="loading.querying || !filters.date_from || !filters.date_to || filters.eqp_types.length === 0"
            @click="emit('submit')"
          >
            <template v-if="loading.querying">查詢中...</template>
            <template v-else>查詢</template>
          </button>
          <button
            type="button"
            class="ui-btn ui-btn--ghost"
            :disabled="loading.querying"
            @click="emit('clear')"
          >
            清除條件
          </button>
        </div>
        <div class="filter-hint">
          日期區間與機台類型為必填。送出後將觸發背景查詢，完成後可使用細部篩選。
        </div>
      </div>
    </div>
  </section>
</template>
