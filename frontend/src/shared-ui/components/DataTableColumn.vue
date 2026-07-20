<script setup lang="ts">
import { inject, onMounted, onUnmounted, watch } from 'vue'

interface ColumnDefinition {
  key: string;
  label: string;
  sortable: boolean;
  width: string | null;
  align: string;
}

interface Props {
  columnKey: string;
  label: string;
  sortable?: boolean;
  width?: string | null;
  align?: 'left' | 'center' | 'right';
}

const props = withDefaults(defineProps<Props>(), {
  sortable: false,
  width: null,
  align: 'left',
});

const registerColumn = inject<((col: ColumnDefinition) => void) | null>('registerColumn', null)
const unregisterColumn = inject<((key: string) => void) | null>('unregisterColumn', null)

function register() {
  registerColumn?.({
    key: props.columnKey,
    label: props.label,
    sortable: props.sortable,
    width: props.width ?? null,
    align: props.align,
  })
}

onMounted(register)

// Re-register on prop change: registerColumn is an upsert, so a dynamically
// computed label (e.g. switching 產出/轉出 modes) stays reflected in the header
// instead of freezing at whatever it was on first mount.
watch(() => [props.label, props.sortable, props.width, props.align], register)

onUnmounted(() => {
  unregisterColumn?.(props.columnKey)
})
</script>

<template>
  <!-- DataTableColumn is a registration-only component; it renders nothing -->
</template>
