import { computed, ref } from 'vue';
import type { Ref, ComputedRef } from 'vue';

export interface PaginationInitial {
  page?: number | string;
  perPage?: number | string;
  total?: number | string;
  totalPages?: number | string;
  [key: string]: unknown;
}

export interface PaginationPayload {
  page?: number | string;
  perPage?: number | string;
  page_size?: number | string;
  total?: number | string;
  total_count?: number | string;
  totalPages?: number | string;
  total_pages?: number | string;
  [key: string]: unknown;
}

export interface PaginationState {
  page: Ref<number>;
  perPage: Ref<number>;
  total: Ref<number>;
  totalPages: Ref<number>;
  hasPrev: ComputedRef<boolean>;
  hasNext: ComputedRef<boolean>;
  setFromPayload: (pagination?: PaginationPayload) => void;
  reset: () => void;
}

export function usePaginationState(initial: PaginationInitial = {}): PaginationState {
  const page = ref(Number(initial.page || 1));
  const perPage = ref(Number(initial.perPage || 50));
  const total = ref(Number(initial.total || 0));
  const totalPages = ref(Number(initial.totalPages || 1));

  const hasPrev: ComputedRef<boolean> = computed(() => page.value > 1);
  const hasNext: ComputedRef<boolean> = computed(() => page.value < totalPages.value);

  function setFromPayload(pagination: PaginationPayload = {}): void {
    page.value = Number(pagination.page || 1);
    perPage.value = Number(pagination.perPage || pagination.page_size || perPage.value || 50);
    total.value = Number(pagination.total || pagination.total_count || 0);
    totalPages.value = Number(pagination.totalPages || pagination.total_pages || 1);
  }

  function reset(): void {
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
