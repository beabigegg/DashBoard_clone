<script setup>
import { computed, useSlots } from 'vue';

const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  cacheLevel: {
    type: String,
    default: '',
  },
  cacheText: {
    type: String,
    default: '',
  },
  lastUpdate: {
    type: String,
    default: '--',
  },
  refreshing: {
    type: Boolean,
    default: false,
  },
  refreshSuccess: {
    type: Boolean,
    default: false,
  },
  refreshError: {
    type: Boolean,
    default: false,
  },
});

defineEmits(['refresh']);

const slots = useSlots();
const hasLeftSlot = computed(() => !!slots['header-left']);

const showCache = computed(() => !!props.cacheText);

const cacheDotClass = computed(() => {
  if (props.cacheLevel === 'ok') return '';
  if (props.cacheLevel === 'error') return 'error';
  return 'loading';
});
</script>

<template>
  <header class="header-gradient">
    <div v-if="hasLeftSlot" class="header-left">
      <slot name="header-left" />
      <h1>{{ title }}</h1>
      <slot name="header-left-after" />
    </div>
    <h1 v-else>{{ title }}</h1>
    <div class="page-header-meta">
      <div v-if="showCache" class="cache-status">
        <span class="cache-dot" :class="cacheDotClass"></span>
        <span>{{ cacheText }}</span>
      </div>
      <span class="last-update">
        <span class="refresh-indicator" :class="{ active: refreshing }"></span>
        <span class="refresh-success" :class="{ active: refreshSuccess }">&#10003;</span>
        <span class="refresh-error-dot" :class="{ active: refreshError }"></span>
        <span>更新: {{ lastUpdate }}</span>
      </span>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" :disabled="refreshing" @click="$emit('refresh')">
        重新整理
      </button>
    </div>
  </header>
</template>
