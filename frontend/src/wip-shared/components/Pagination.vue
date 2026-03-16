<script setup>
import { computed } from 'vue';

const props = defineProps({
  page: {
    type: Number,
    default: 1,
  },
  totalPages: {
    type: Number,
    default: 1,
  },
  infoText: {
    type: String,
    default: '',
  },
  visible: {
    type: Boolean,
    default: true,
  },
});

const emit = defineEmits(['prev', 'next']);

const canPrev = computed(() => props.page > 1);
const canNext = computed(() => props.page < props.totalPages);
</script>

<template>
  <div v-if="visible" class="pagination">
    <button type="button" :disabled="!canPrev" aria-label="上一頁" @click="emit('prev')">上一頁</button>
    <span class="page-info">{{ infoText || `第 ${page} / ${totalPages} 頁` }}</span>
    <button type="button" :disabled="!canNext" aria-label="下一頁" @click="emit('next')">下一頁</button>
  </div>
</template>
