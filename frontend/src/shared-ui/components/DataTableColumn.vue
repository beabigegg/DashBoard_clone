<script setup lang="ts">
import { inject, onMounted, onUnmounted } from 'vue'

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

onMounted(() => {
  registerColumn?.({
    key: props.columnKey,
    label: props.label,
    sortable: props.sortable,
    width: props.width ?? null,
    align: props.align,
  })
})

onUnmounted(() => {
  unregisterColumn?.(props.columnKey)
})
</script>

<template>
  <!-- DataTableColumn is a registration-only component; it renders nothing -->
</template>
