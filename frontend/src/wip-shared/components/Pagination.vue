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
    <button type="button" :disabled="!canPrev" @click="emit('prev')">Prev</button>
    <span class="page-info">{{ infoText || `Page ${page} / ${totalPages}` }}</span>
    <button type="button" :disabled="!canNext" @click="emit('next')">Next</button>
  </div>
</template>
