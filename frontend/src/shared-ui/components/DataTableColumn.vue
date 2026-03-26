<script setup>
import { inject, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  columnKey: {
    type: String,
    required: true
  },
  label: {
    type: String,
    required: true
  },
  sortable: {
    type: Boolean,
    default: false
  },
  width: {
    type: String,
    default: null
  },
  align: {
    type: String,
    default: 'left',
    validator: (v) => ['left', 'center', 'right'].includes(v)
  }
})

const registerColumn = inject('registerColumn', null)
const unregisterColumn = inject('unregisterColumn', null)

onMounted(() => {
  registerColumn?.({
    key: props.columnKey,
    label: props.label,
    sortable: props.sortable,
    width: props.width,
    align: props.align
  })
})

onUnmounted(() => {
  unregisterColumn?.(props.columnKey)
})
</script>

<template>
  <!-- DataTableColumn is a registration-only component; it renders nothing -->
</template>
