<script setup>
import { computed } from 'vue';

import BasePagination from '../../wip-shared/components/Pagination.vue';

const props = defineProps({
  page: {
    type: Number,
    default: null,
  },
  modelValue: {
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

const emit = defineEmits(['update:modelValue', 'change', 'prev', 'next']);

const page = computed(() => {
  if (props.page !== null && props.page !== undefined) {
    return Number(props.page || 1);
  }
  return Number(props.modelValue || 1);
});
const safeTotalPages = computed(() => Math.max(Number(props.totalPages || 1), 1));

function toPage(nextPage, eventName) {
  if (nextPage < 1 || nextPage > safeTotalPages.value || nextPage === page.value) {
    return;
  }
  emit('update:modelValue', nextPage);
  emit('change', nextPage);
  emit(eventName, nextPage);
}

function onPrev() {
  toPage(page.value - 1, 'prev');
}

function onNext() {
  toPage(page.value + 1, 'next');
}
</script>

<template>
  <BasePagination
    :visible="visible"
    :page="page"
    :total-pages="safeTotalPages"
    :info-text="infoText"
    @prev="onPrev"
    @next="onNext"
  />
</template>
