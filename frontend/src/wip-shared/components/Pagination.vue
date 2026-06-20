<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  page?: number;
  totalPages?: number;
  infoText?: string;
  visible?: boolean;
}>();

const emit = defineEmits(['prev', 'next']);

const canPrev = computed(() => (props.page ?? 1) > 1);
const canNext = computed(() => (props.page ?? 1) < (props.totalPages ?? 1));
</script>

<template>
  <div v-if="visible !== false" class="pagination">
    <button type="button" class="ui-btn ui-btn--ghost" :disabled="!canPrev" aria-label="上一頁" data-testid="page-prev" @click="emit('prev')">上一頁</button>
    <span class="page-info" data-testid="page-info">{{ infoText || `第 ${page ?? 1} / ${totalPages ?? 1} 頁` }}</span>
    <button type="button" class="ui-btn ui-btn--ghost" :disabled="!canNext" aria-label="下一頁" data-testid="page-next" @click="emit('next')">下一頁</button>
  </div>
</template>
