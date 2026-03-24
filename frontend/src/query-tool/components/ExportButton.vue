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
    class="ui-btn ui-btn--secondary"
    :disabled="disabled || loading"
  >
    {{ loading ? '匯出中...' : label }}
  </button>
</template>
