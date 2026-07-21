<script setup lang="ts">
/**
 * FilterPanel — equipment-lookup (機台查詢)
 *
 * Inputs: 機台位置 (locations) / 機型 (families) / 編號 (resource_names) — 3
 * independent MultiSelects with NO cross-filter narrowing (options load once
 * from the parent's /options call and never change based on sibling
 * selections — deliberate, matches the backend's non-narrowing behavior).
 * Emits: query-submit, reset
 */
import { ref } from 'vue';
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';
import type { ListFilters } from '../composables/useEquipmentLookup';

withDefaults(
  defineProps<{
    locationOptions?: string[];
    familyOptions?: string[];
    resourceNameOptions?: string[];
    loading?: boolean;
  }>(),
  {
    locationOptions: () => [],
    familyOptions: () => [],
    resourceNameOptions: () => [],
    loading: false,
  }
);

const emit = defineEmits<{
  (e: 'query-submit', payload: ListFilters): void;
  (e: 'reset'): void;
}>();

// --- State ---
const selectedLocations = ref<string[]>([]);
const selectedFamilies = ref<string[]>([]);
const selectedResourceNames = ref<string[]>([]);

function handleSubmit() {
  emit('query-submit', {
    locations: selectedLocations.value,
    families: selectedFamilies.value,
    resource_names: selectedResourceNames.value,
  });
}

function handleReset() {
  selectedLocations.value = [];
  selectedFamilies.value = [];
  selectedResourceNames.value = [];
  emit('reset');
}
</script>

<template>
  <div class="filter-panel-wrap">
    <div class="filter-grid">
      <!-- 機台位置 -->
      <div class="filter-group">
        <span id="label-location" class="filter-label">機台位置</span>
        <div role="group" aria-labelledby="label-location">
          <MultiSelect
            v-model="selectedLocations"
            :options="locationOptions"
            placeholder="全部機台位置"
            :disabled="loading"
            data-testid="location-select"
          />
        </div>
      </div>

      <!-- 機型 -->
      <div class="filter-group">
        <span id="label-family" class="filter-label">機型</span>
        <div role="group" aria-labelledby="label-family">
          <MultiSelect
            v-model="selectedFamilies"
            :options="familyOptions"
            placeholder="全部機型"
            :disabled="loading"
            data-testid="family-select"
          />
        </div>
      </div>

      <!-- 編號 (searchable) -->
      <div class="filter-group">
        <span id="label-resource-name" class="filter-label">編號</span>
        <div role="group" aria-labelledby="label-resource-name">
          <MultiSelect
            v-model="selectedResourceNames"
            :options="resourceNameOptions"
            :searchable="true"
            placeholder="全部編號（可搜尋）"
            :disabled="loading"
            data-testid="resource-name-select"
          />
        </div>
      </div>
    </div>

    <!-- Action buttons -->
    <div class="filter-actions">
      <button
        type="button"
        class="ui-btn ui-btn--primary"
        :disabled="loading"
        data-testid="query-submit-button"
        @click="handleSubmit"
      >
        {{ loading ? '查詢中...' : '查詢' }}
      </button>
      <button
        type="button"
        class="ui-btn ui-btn--secondary"
        data-testid="reset-button"
        @click="handleReset"
      >
        重置
      </button>
    </div>
  </div>
</template>
