<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  options: {
    type: Array,
    default: () => [],
  },
  placeholder: {
    type: String,
    default: '請選擇',
  },
  disabled: {
    type: Boolean,
    default: false,
  },
  searchable: {
    type: Boolean,
    default: true,
  },
  selectAllScope: {
    type: String,
    default: 'visible',
    validator: (v) => ['visible', 'all'].includes(v),
  },
});

const emit = defineEmits(['update:modelValue']);

const rootRef = ref(null);
const searchRef = ref(null);
const isOpen = ref(false);
const searchQuery = ref('');

const normalizedOptions = computed(() => {
  return props.options.map((option) => {
    if (option && typeof option === 'object') {
      const value = option.value ?? option.name ?? option.label ?? '';
      const label = option.label ?? option.name ?? option.value ?? '';
      return { label: String(label), value: String(value) };
    }
    return { label: String(option), value: String(option) };
  });
});

const displayedOptions = computed(() => {
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

function isSelected(value) {
  return selectedSet.value.has(String(value));
}

function toggleOption(value) {
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
  emit('update:modelValue', next);
}

function handleOutsideClick(event) {
  if (!isOpen.value || !rootRef.value) return;
  if (!rootRef.value.contains(event.target)) isOpen.value = false;
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
