<script setup>
import { computed } from 'vue';

const props = defineProps({
  cacheLevel: {
    type: String,
    default: 'loading',
  },
  cacheText: {
    type: String,
    default: '檢查中...',
  },
  lastUpdate: {
    type: String,
    default: '--',
  },
  refreshing: {
    type: Boolean,
    default: false,
  },
});

defineEmits(['refresh']);

const cacheDotClass = computed(() => {
  if (props.cacheLevel === 'ok') {
    return '';
  }
  if (props.cacheLevel === 'error') {
    return 'error';
  }
  return 'loading';
});
</script>

<template>
  <header class="header-gradient">
    <h1>設備即時概況</h1>
    <div class="status-header-meta">
      <div class="cache-status">
        <span class="cache-dot" :class="cacheDotClass"></span>
        <span>{{ cacheText }}</span>
      </div>
      <span class="last-update">更新: {{ lastUpdate }}</span>
      <button type="button" class="btn btn-primary" :disabled="refreshing" @click="$emit('refresh')">
        重新整理
      </button>
    </div>
  </header>
</template>
