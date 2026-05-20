<script setup lang="ts">
/**
 * FilterPanel — material-consumption
 * Change: material-part-consumption
 *
 * Inputs: material_parts (MultiSelect fuzzy search), start_date, end_date, granularity, Type MultiSelect
 * Emits: query-submit, granularity-change, type-change, reset
 * Validates: 20-part cap client-side (AC-2 / MC-02)
 */
import { computed, ref } from 'vue';
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';
import type { Granularity } from '../composables/useConsumptionQuery';

// --- Props ---
const props = withDefaults(
  defineProps<{
    partOptions?: Array<{ name: string; description?: string | null }>;
    loading?: boolean;
  }>(),
  {
    partOptions: () => [],
    loading: false,
  }
);

const emit = defineEmits<{
  (e: 'query-submit', payload: {
    material_parts: string[];
    start_date: string;
    end_date: string;
    granularity: Granularity;
  }): void;
  (e: 'granularity-change', granularity: Granularity): void;
  (e: 'reset'): void;
}>();

// --- State ---
const selectedParts = ref<string[]>([]);
const startDate = ref('');
const endDate = ref('');
const granularity = ref<Granularity>('week');
const validationError = ref('');

// --- Computed ---
const partCount = computed(() => selectedParts.value.length);
const isOverCap = computed(() => partCount.value > 20);

// Display strings for MultiSelect options (shows "NAME — description" when description exists)
const partDisplayOptions = computed(() =>
  props.partOptions.map(p =>
    p.description ? `${p.name} — ${p.description}` : p.name
  )
);

// Reverse map: display string → raw part name (for submit payload)
const partNameByDisplay = computed(() => {
  const m: Record<string, string> = {};
  props.partOptions.forEach(p => {
    const display = p.description ? `${p.name} — ${p.description}` : p.name;
    m[display] = p.name;
  });
  return m;
});

const canSubmit = computed(
  () =>
    selectedParts.value.length > 0 &&
    !isOverCap.value &&
    !!startDate.value &&
    !!endDate.value &&
    !props.loading
);

// --- Methods ---
function handleGranularityChange(g: Granularity) {
  granularity.value = g;
  emit('granularity-change', g);
}

function handleSubmit() {
  validationError.value = '';

  if (selectedParts.value.length === 0) {
    validationError.value = '請選擇料號';
    return;
  }
  if (isOverCap.value) {
    validationError.value = `料號數量超過上限（最多 20 個，目前 ${partCount.value} 個）`;
    return;
  }
  if (!startDate.value || !endDate.value) {
    validationError.value = '請選擇日期範圍';
    return;
  }

  emit('query-submit', {
    material_parts: selectedParts.value.map(d => partNameByDisplay.value[d] ?? d),
    start_date: startDate.value,
    end_date: endDate.value,
    granularity: granularity.value,
  });
}

function handleReset() {
  selectedParts.value = [];
  startDate.value = '';
  endDate.value = '';
  granularity.value = 'week';
  validationError.value = '';
  emit('reset');
}
</script>

<template>
  <div class="filter-panel-wrap">
    <!-- Validation error -->
    <div
      v-if="validationError"
      class="validation-error"
      role="alert"
      data-testid="validation-error"
    >
      {{ validationError }}
    </div>

    <div class="filter-grid">
      <!-- Material Parts — MultiSelect with fuzzy search (replaces textarea) -->
      <div class="filter-group filter-group--full">
        <div role="group" aria-labelledby="label-parts">
          <span id="label-parts" class="filter-label">料號（支援模糊搜尋，最多 20 個）</span>
          <MultiSelect
            v-model="selectedParts"
            :options="partDisplayOptions"
            placeholder="輸入料號搜尋..."
            :disabled="loading"
            data-testid="material-parts-select"
          />
        </div>
        <div
          class="input-count"
          :class="{ 'input-count--error': isOverCap }"
        >
          已選 {{ partCount }} 個料號
          <template v-if="isOverCap">（超過上限 20 個）</template>
        </div>
      </div>

      <!-- Date range -->
      <div class="filter-group">
        <label class="filter-label" for="start-date">開始日期</label>
        <input
          id="start-date"
          v-model="startDate"
          type="date"
          class="filter-input"
          data-testid="start-date"
        />
      </div>
      <div class="filter-group">
        <label class="filter-label" for="end-date">結束日期</label>
        <input
          id="end-date"
          v-model="endDate"
          type="date"
          class="filter-input"
          data-testid="end-date"
        />
      </div>

      <!-- Granularity — includes 'day' option -->
      <div class="filter-group filter-group--granularity">
        <label class="filter-label">時間粒度</label>
        <div class="granularity-buttons">
          <button
            v-for="g in (['day', 'week', 'month', 'quarter'] as const)"
            :key="g"
            type="button"
            class="granularity-btn"
            :class="{ 'granularity-btn--active': granularity === g }"
            :data-granularity="g"
            :aria-pressed="granularity === g"
            @click="handleGranularityChange(g)"
          >
            {{ g === 'day' ? '日' : g === 'week' ? '週' : g === 'month' ? '月' : '季' }}
          </button>
        </div>
      </div>

    </div>

    <!-- Action buttons -->
    <div class="filter-actions">
      <button
        type="button"
        class="ui-btn ui-btn--primary"
        :disabled="!canSubmit"
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
        清除
      </button>
    </div>
  </div>
</template>
