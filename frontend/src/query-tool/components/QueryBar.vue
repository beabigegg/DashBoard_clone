<script setup lang="ts">
import { computed } from 'vue';

import FilterToolbar from '../../shared-ui/components/FilterToolbar.vue';

const props = defineProps({
  inputType: {
    type: String,
    default: 'lot_id',
  },
  inputText: {
    type: String,
    default: '',
  },
  inputTypeOptions: {
    type: Array,
    default: () => [],
  },
  inputLimit: {
    type: Number,
    default: 50,
  },
  resolving: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['update:inputType', 'update:inputText', 'resolve']);

const inputCount = computed(() => {
  return String(props.inputText || '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .length;
});

const inputTypeLabel = computed(() => {
  const selected = (props.inputTypeOptions || []).find((option) => (option as Record<string, unknown>)?.value === props.inputType);
  return (selected as Record<string, unknown>)?.label as string || '查詢條件';
});

function handleResolve() {
  emit('resolve');
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-body ui-card-body">
      <FilterToolbar>
        <label class="filter-group">
          <span class="filter-label">查詢類型</span>
          <select
            class="query-tool-select"
            :value="inputType"
            :disabled="resolving"
            @change="emit('update:inputType', ($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="option in inputTypeOptions"
              :key="(option as Record<string, unknown>).value as PropertyKey"
              :value="(option as Record<string, unknown>).value"
            >
              {{ (option as Record<string, unknown>).label }}
            </option>
          </select>
        </label>

        <template #actions>
          <button
            type="button"
            class="ui-btn ui-btn--primary"
            :disabled="resolving"
            data-testid="submit-btn"
            @click="handleResolve"
          >
            {{ resolving ? '解析中...' : '解析' }}
          </button>
        </template>
      </FilterToolbar>

      <div class="mt-filter-section">
        <textarea
          :value="inputText"
          class="query-tool-textarea"
          data-testid="lot-input"
          :placeholder="`請輸入 ${inputTypeLabel}（換行或逗號分隔），最多 ${inputLimit} 筆`"
          :disabled="resolving"
          @input="emit('update:inputText', ($event.target as HTMLTextAreaElement).value)"
        />
        <p class="query-tool-input-help">
          支援萬用字元：<code>%</code>（任意長度）、<code>_</code>（單一字元），也可用 <code>*</code> 代表 <code>%</code>。
          例如：<code>GA25%01</code>、<code>GA25%</code>、<code>GMSN-1173%</code>
        </p>
        <div class="query-tool-input-counter">
          <span>已輸入 {{ inputCount }} / {{ inputLimit }}</span>
          <span v-if="errorMessage" class="query-tool-input-error">{{ errorMessage }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.mt-filter-section {
  margin-top: theme('spacing.token.p12');
}
</style>
