import { ref } from 'vue';
import type { Ref } from 'vue';

export interface RequestGuard {
  nextRequestId: () => number;
  isStaleRequest: (id: number) => boolean;
}

export function useRequestGuard(): RequestGuard {
  const currentId: Ref<number> = ref(0);

  function nextRequestId(): number {
    currentId.value += 1;
    return currentId.value;
  }

  function isStaleRequest(id: number): boolean {
    return id !== currentId.value;
  }

  return { nextRequestId, isStaleRequest };
}
