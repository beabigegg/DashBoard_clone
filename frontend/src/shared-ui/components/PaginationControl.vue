<script setup lang="ts">
import { computed } from 'vue';

import BasePagination from '../../wip-shared/components/Pagination.vue';

interface Props {
  page?: number | null;
  modelValue?: number;
  totalPages?: number;
  infoText?: string;
  visible?: boolean;
  showPageNumbers?: boolean;
  showPageSize?: boolean;
  pageSizeOptions?: number[];
  pageSize?: number | null;
}

const props = withDefaults(defineProps<Props>(), {
  page: null,
  modelValue: 1,
  totalPages: 1,
  infoText: '',
  visible: true,
  showPageNumbers: false,
  showPageSize: false,
  pageSizeOptions: () => [10, 25, 50, 100],
  pageSize: null,
});

const emit = defineEmits<{
  (e: 'update:modelValue', page: number): void;
  (e: 'change', page: number): void;
  (e: 'prev', page: number): void;
  (e: 'next', page: number): void;
  (e: 'update:pageSize', size: number): void;
}>();

const page = computed(() => {
  if (props.page !== null && props.page !== undefined) {
    return Number(props.page || 1);
  }
  return Number(props.modelValue || 1);
});
const safeTotalPages = computed(() => Math.max(Number(props.totalPages || 1), 1));

function toPage(nextPage: number, eventName: 'prev' | 'next' | 'change') {
  if (nextPage < 1 || nextPage > safeTotalPages.value || nextPage === page.value) {
    return;
  }
  emit('update:modelValue', nextPage);
  emit('change', nextPage);
  if (eventName === 'prev') emit('prev', nextPage);
  else if (eventName === 'next') emit('next', nextPage);
}

function onPrev() {
  toPage(page.value - 1, 'prev');
}

function onNext() {
  toPage(page.value + 1, 'next');
}

function onPageInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value);
  if (!Number.isNaN(val) && val >= 1 && val <= safeTotalPages.value) {
    toPage(val, 'change');
  }
}

function onPageSizeChange(e: Event) {
  const val = Number((e.target as HTMLSelectElement).value);
  if (!Number.isNaN(val) && val > 0) {
    emit('update:pageSize', val);
    toPage(1, 'change');
  }
}

const pageNumbers = computed((): (number | string)[] => {
  if (!props.showPageNumbers) return [];
  const total = safeTotalPages.value;
  const current = page.value;
  const delta = 2;
  const range: number[] = [];
  const pages: (number | string)[] = [];

  for (let i = Math.max(1, current - delta); i <= Math.min(total, current + delta); i++) {
    range.push(i);
  }
  if (range[0] > 1) {
    pages.push(1);
    if (range[0] > 2) pages.push('...');
  }
  range.forEach((p) => pages.push(p));
  if (range[range.length - 1] < total) {
    if (range[range.length - 1] < total - 1) pages.push('...');
    pages.push(total);
  }
  return pages;
});
</script>

<template>
  <div v-if="visible" class="pagination-control-wrap">
    <!-- Page size selector -->
    <label v-if="showPageSize" class="pagination-page-size">
      每頁
      <select
        :value="pageSize || pageSizeOptions[0]"
        aria-label="每頁顯示筆數"
        @change="onPageSizeChange"
      >
        <option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
      </select>
      筆
    </label>

    <!-- Page number buttons -->
    <div v-if="showPageNumbers" class="pagination-page-numbers">
      <button
        v-for="p in pageNumbers"
        :key="p"
        type="button"
        class="pagination-page-btn"
        :class="{ active: p === page }"
        :disabled="p === '...'"
        :aria-label="p !== '...' ? `第 ${p} 頁` : undefined"
        :aria-current="p === page ? 'page' : undefined"
        @click="p !== '...' && toPage(p as number, 'change')"
      >
        {{ p }}
      </button>
    </div>

    <!-- Base prev/next pagination -->
    <BasePagination
      :visible="true"
      :page="page"
      :total-pages="safeTotalPages"
      :info-text="infoText"
      @prev="onPrev"
      @next="onNext"
    />

    <!-- Jump to page input -->
    <label v-if="showPageNumbers && safeTotalPages > 5" class="pagination-jump">
      跳至
      <input
        type="number"
        :min="1"
        :max="safeTotalPages"
        :value="page"
        aria-label="跳至頁碼"
        class="pagination-jump-input"
        @change="onPageInput"
      />
      頁
    </label>
  </div>
</template>

<style scoped>
.pagination-control-wrap {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.pagination-page-size {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: theme('colors.text.subtle');
}

.pagination-page-size select {
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 4px;
  padding: 2px 4px;
  font-size: 13px;
}

.pagination-page-numbers {
  display: flex;
  align-items: center;
  gap: 2px;
}

.pagination-page-btn {
  min-width: 28px;
  height: 28px;
  padding: 0 6px;
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 4px;
  background: theme('colors.surface.card');
  font-size: 12px;
  cursor: pointer;
}

.pagination-page-btn.active {
  background: theme('colors.brand.500');
  color: white;
  border-color: theme('colors.brand.500');
}

.pagination-page-btn:disabled {
  cursor: default;
  border: none;
}

.pagination-jump {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: theme('colors.text.subtle');
}

.pagination-jump-input {
  width: 52px;
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 4px;
  padding: 2px 4px;
  font-size: 13px;
  text-align: center;
}
</style>
