<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import LoadingSpinner from './LoadingSpinner.vue';

interface NormalizedOption {
  label: string;
  value: string;
}

interface Props {
  modelValue?: (string | number)[];
  options?: (string | number | Record<string, unknown>)[];
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  searchable?: boolean;
  selectAllScope?: 'visible' | 'all';
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  options: () => [],
  placeholder: '請選擇',
  disabled: false,
  loading: false,
  searchable: true,
  selectAllScope: 'visible',
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void;
}>();

const rootRef = ref<HTMLElement | null>(null);
const searchRef = ref<HTMLInputElement | null>(null);
const isOpen = ref(false);
const searchQuery = ref('');

const normalizedOptions = computed((): NormalizedOption[] => {
  return props.options.map((option) => {
    if (option && typeof option === 'object') {
      const opt = option as Record<string, unknown>;
      const value = opt.value ?? opt.name ?? opt.label ?? '';
      const label = opt.label ?? opt.name ?? opt.value ?? '';
      return { label: String(label), value: String(value) };
    }
    return { label: String(option), value: String(option) };
  });
});

const displayedOptions = computed((): NormalizedOption[] => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return normalizedOptions.value;
  return normalizedOptions.value.filter(
    (opt) => opt.label.toLowerCase().includes(q) || opt.value.toLowerCase().includes(q)
  );
});

const selectedSet = computed(() => new Set((props.modelValue || []).map((v) => String(v))));

const selectedText = computed(() => {
  if (!props.modelValue.length) return props.placeholder;
  if (props.modelValue.length === 1) {
    const found = normalizedOptions.value.find((o) => o.value === String(props.modelValue[0]));
    return found?.label || String(props.modelValue[0]);
  }
  return `已選 ${props.modelValue.length} 項`;
});

function closeDropdown() {
  isOpen.value = false;
}

function toggleDropdown() {
  if (props.disabled) return;
  isOpen.value = !isOpen.value;
}

function isSelected(value: string) {
  return selectedSet.value.has(String(value));
}

function toggleOption(value: string) {
  const next = new Set(selectedSet.value);
  const key = String(value);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  emit('update:modelValue', [...next]);
}

function selectAll() {
  const scope = props.selectAllScope === 'all' ? normalizedOptions.value : displayedOptions.value;
  const next = new Set(selectedSet.value);
  for (const opt of scope) next.add(opt.value);
  emit('update:modelValue', [...next]);
}

function clearAll() {
  if (!searchQuery.value) {
    emit('update:modelValue', []);
    return;
  }
  const removing = new Set(displayedOptions.value.map((o) => o.value));
  const next = props.modelValue.filter((v) => !removing.has(String(v)));
  emit('update:modelValue', next.map(String));
}

function handleOutsideClick(event: MouseEvent) {
  if (!isOpen.value || !rootRef.value) return;
  if (!rootRef.value.contains(event.target as Node)) isOpen.value = false;
}

watch(isOpen, (open) => {
  if (open && props.searchable) {
    searchQuery.value = '';
    requestAnimationFrame(() => searchRef.value?.focus());
  }
});

onMounted(() => document.addEventListener('click', handleOutsideClick, true));
onBeforeUnmount(() => document.removeEventListener('click', handleOutsideClick, true));
</script>

<template>
  <div ref="rootRef" class="multi-select">
    <button
      type="button"
      class="multi-select-trigger"
      :disabled="disabled || loading"
      @click="toggleDropdown"
    >
      <span class="multi-select-text">{{ selectedText }}</span>
      <!-- Loading spinner using shared component -->
      <span v-if="loading" class="multi-select-spinner" aria-hidden="true">
        <LoadingSpinner size="sm" />
      </span>
      <!-- SVG chevron (Task 5.3) -->
      <span v-else class="multi-select-arrow" :class="{ 'is-open': isOpen }" aria-hidden="true">
        <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg" class="ms-chevron-icon">
          <path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </span>
    </button>

    <div v-if="isOpen && !loading" class="multi-select-dropdown">
      <input
        v-if="searchable"
        ref="searchRef"
        v-model="searchQuery"
        type="text"
        class="multi-select-search"
        placeholder="搜尋..."
        @click.stop
      />

      <div class="multi-select-options">
        <button
          v-for="option in displayedOptions"
          :key="option.value"
          type="button"
          class="multi-select-option"
          @click="toggleOption(option.value)"
        >
          <input type="checkbox" :checked="isSelected(option.value)" tabindex="-1" />
          <span>{{ option.label }}</span>
        </button>
        <div v-if="displayedOptions.length === 0" class="multi-select-empty">
          無符合結果
        </div>
      </div>

      <div class="multi-select-actions">
        <button type="button" class="ui-btn ui-btn--sm" @click="selectAll">全選</button>
        <button type="button" class="ui-btn ui-btn--sm" @click="clearAll">清除</button>
        <button type="button" class="ui-btn ui-btn--sm" @click="closeDropdown">關閉</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.multi-select-spinner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.multi-select-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform var(--motion-fast, 150ms) var(--motion-ease, cubic-bezier(0.4, 0, 0.2, 1));
}

.multi-select-arrow.is-open {
  transform: rotate(180deg);
}

.ms-chevron-icon {
  width: 14px;
  height: 14px;
  color: currentColor;
}

/* === Base structural styles (no theme dependency) === */
.multi-select {
  position: relative;
  min-width: 200px;
}

.multi-select-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.multi-select-trigger:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.multi-select-options {
  max-height: 250px;
  overflow-y: auto;
}

@media (max-width: 640px) {
  .multi-select {
    min-width: 150px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .multi-select-arrow {
    transition: none;
  }
}
</style>
