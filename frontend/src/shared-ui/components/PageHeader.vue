<script setup lang="ts">
import { computed, useSlots } from 'vue';

interface Props {
  title: string;
  cacheLevel?: string;
  cacheText?: string;
  lastUpdate?: string;
  refreshing?: boolean;
  refreshSuccess?: boolean;
  refreshError?: boolean;
  showRefresh?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  cacheLevel: '',
  cacheText: '',
  lastUpdate: '--',
  refreshing: false,
  refreshSuccess: false,
  refreshError: false,
  showRefresh: true,
});

defineEmits<{
  (e: 'refresh'): void;
}>();

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
    <div class="header-title-block">
      <div v-if="hasLeftSlot" class="header-left">
        <slot name="header-left" />
        <h1>{{ title }}</h1>
        <slot name="header-left-after" />
      </div>
      <h1 v-else>{{ title }}</h1>
      <div v-if="$slots.subtitle" class="header-subtitle">
        <slot name="subtitle" />
      </div>
    </div>
    <div v-if="showRefresh" class="page-header-meta">
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

<style scoped>
.header-gradient {
  background: linear-gradient(135deg, theme('colors.brand.700') 0%, theme('colors.brand.500') 100%);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.header-subtitle {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.75);
  margin-top: 4px;
}

.header-title-block {
  display: flex;
  flex-direction: column;
}
</style>
