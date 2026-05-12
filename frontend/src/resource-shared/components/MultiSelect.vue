<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

type OptionObject = {
  value?: string | number;
  name?: string | number;
  label?: string | number;
};

const props = defineProps<{
  modelValue?: string[];
  options?: Array<OptionObject | string | number>;
  placeholder?: string;
  disabled?: boolean;
  searchable?: boolean;
}>();

const emit = defineEmits(['update:modelValue']);

const rootRef = ref<HTMLElement | null>(null);
const searchRef = ref<HTMLInputElement | null>(null);
const isOpen = ref(false);
const searchQuery = ref('');

const resolvedModelValue = computed<string[]>(() => props.modelValue ?? []);
const resolvedOptions = computed<Array<OptionObject | string | number>>(() => props.options ?? []);
const resolvedPlaceholder = computed<string>(() => props.placeholder ?? '請選擇');

const normalizedOptions = computed(() => {
  return resolvedOptions.value.map((option) => {
    if (option && typeof option === 'object') {
      const obj = option as OptionObject;
      const value = obj.value ?? obj.name ?? obj.label ?? '';
      const label = obj.label ?? obj.name ?? obj.value ?? '';
      return {
        label: String(label),
        value: String(value),
      };
    }

    return {
      label: String(option),
      value: String(option),
    };
  });
});

const displayedOptions = computed(() => {
  if (!searchQuery.value) {
    return normalizedOptions.value;
  }
  const q = searchQuery.value.toLowerCase();
  return normalizedOptions.value.filter((opt) => opt.label.toLowerCase().includes(q));
});

const selectedSet = computed(
  () => new Set(resolvedModelValue.value.map((value) => String(value)))
);

const selectedText = computed(() => {
  if (!resolvedModelValue.value.length) {
    return resolvedPlaceholder.value;
  }

  if (resolvedModelValue.value.length === 1) {
    const found = normalizedOptions.value.find(
      (option) => option.value === String(resolvedModelValue.value[0])
    );
    return found?.label || String(resolvedModelValue.value[0]);
  }

  return `已選 ${resolvedModelValue.value.length} 項`;
});

function closeDropdown(): void {
  isOpen.value = false;
}

function toggleDropdown(): void {
  if (props.disabled) {
    return;
  }
  isOpen.value = !isOpen.value;
}

function isSelected(value: string): boolean {
  return selectedSet.value.has(String(value));
}

function toggleOption(value: string): void {
  const next = new Set(selectedSet.value);
  const key = String(value);

  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }

  emit('update:modelValue', [...next]);
}

function selectAll(): void {
  const next = new Set(selectedSet.value);
  for (const opt of displayedOptions.value) {
    next.add(opt.value);
  }
  emit('update:modelValue', [...next]);
}

function clearAll(): void {
  if (!searchQuery.value) {
    emit('update:modelValue', []);
    return;
  }
  const removing = new Set(displayedOptions.value.map((o) => o.value));
  const next = resolvedModelValue.value.filter((v) => !removing.has(String(v)));
  emit('update:modelValue', next);
}

function handleOutsideClick(event: MouseEvent): void {
  if (!isOpen.value || !rootRef.value) {
    return;
  }

  if (!rootRef.value.contains(event.target as Node)) {
    isOpen.value = false;
  }
}

watch(isOpen, (open) => {
  if (open && props.searchable) {
    searchQuery.value = '';
    requestAnimationFrame(() => searchRef.value?.focus());
  }
});

onMounted(() => {
  document.addEventListener('click', handleOutsideClick, true);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick, true);
});
</script>

<template>
  <div ref="rootRef" class="multi-select">
    <button
      type="button"
      class="multi-select-trigger"
      :disabled="disabled"
      @click="toggleDropdown"
    >
      <span class="multi-select-text">{{ selectedText }}</span>
      <span class="multi-select-arrow">{{ isOpen ? '▲' : '▼' }}</span>
    </button>

    <div v-if="isOpen" class="multi-select-dropdown">
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
        <div v-if="searchable && displayedOptions.length === 0" class="multi-select-empty">
          無符合結果
        </div>
      </div>

      <div class="multi-select-actions">
        <button type="button" class="btn-sm" @click="selectAll">全選</button>
        <button type="button" class="btn-sm" @click="clearAll">清除</button>
        <button type="button" class="btn-sm" @click="closeDropdown">關閉</button>
      </div>
    </div>
  </div>
</template>
