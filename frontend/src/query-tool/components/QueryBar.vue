<script setup>
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
  const selected = (props.inputTypeOptions || []).find((option) => option?.value === props.inputType);
  return selected?.label || '查詢條件';
});

function handleResolve() {
  emit('resolve');
}
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3 shadow-soft">
    <FilterToolbar>
      <label class="flex min-w-[220px] flex-col gap-1 text-xs text-slate-500">
        <span class="font-medium">查詢類型</span>
        <select
          class="h-9 rounded-card border border-stroke-soft bg-white px-3 text-sm text-slate-700 outline-none focus:border-brand-500"
          :value="inputType"
          :disabled="resolving"
          @change="emit('update:inputType', $event.target.value)"
        >
          <option
            v-for="option in inputTypeOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
      </label>

      <template #actions>
        <button
          type="button"
          class="h-9 rounded-card bg-brand-500 px-4 text-sm font-medium text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="resolving"
          @click="handleResolve"
        >
          {{ resolving ? '解析中...' : '解析' }}
        </button>
      </template>
    </FilterToolbar>

    <div class="mt-3">
      <textarea
        :value="inputText"
        class="min-h-28 w-full rounded-card border border-stroke-soft bg-surface-muted/40 px-3 py-2 text-sm text-slate-700 outline-none transition focus:border-brand-500"
        :placeholder="`請輸入 ${inputTypeLabel}（換行或逗號分隔），最多 ${inputLimit} 筆`"
        :disabled="resolving"
        @input="emit('update:inputText', $event.target.value)"
      />
      <p class="mt-2 text-xs text-slate-500">
        支援萬用字元：<code>%</code>（任意長度）、<code>_</code>（單一字元），也可用 <code>*</code> 代表 <code>%</code>。
        例如：<code>GA25%01</code>、<code>GA25%</code>、<code>GMSN-1173%</code>
      </p>
      <div class="mt-2 flex items-center justify-between text-xs">
        <p class="text-slate-500">已輸入 {{ inputCount }} / {{ inputLimit }}</p>
        <p v-if="errorMessage" class="text-state-danger">{{ errorMessage }}</p>
      </div>
    </div>
  </section>
</template>
