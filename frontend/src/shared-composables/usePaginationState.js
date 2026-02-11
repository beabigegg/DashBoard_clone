import { computed, ref } from 'vue';

export function usePaginationState(initial = {}) {
  const page = ref(Number(initial.page || 1));
  const perPage = ref(Number(initial.perPage || 50));
  const total = ref(Number(initial.total || 0));
  const totalPages = ref(Number(initial.totalPages || 1));

  const hasPrev = computed(() => page.value > 1);
  const hasNext = computed(() => page.value < totalPages.value);

  function setFromPayload(pagination = {}) {
    page.value = Number(pagination.page || 1);
    perPage.value = Number(pagination.perPage || pagination.page_size || perPage.value || 50);
    total.value = Number(pagination.total || pagination.total_count || 0);
    totalPages.value = Number(pagination.totalPages || pagination.total_pages || 1);
  }

  function reset() {
    page.value = 1;
    total.value = 0;
    totalPages.value = 1;
  }

  return {
    page,
    perPage,
    total,
    totalPages,
    hasPrev,
    hasNext,
    setFromPayload,
    reset,
  };
}
