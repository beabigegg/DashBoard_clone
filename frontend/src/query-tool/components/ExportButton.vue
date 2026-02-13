<script setup>
const props = defineProps({
  disabled: {
    type: Boolean,
    default: false,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  label: {
    type: String,
    default: '匯出 CSV',
  },
});
</script>

<template>
  <button
    type="button"
    class="rounded-card bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
    :disabled="disabled || loading"
  >
    {{ loading ? '匯出中...' : label }}
  </button>
</template>
