import { ref } from 'vue';

export function useRequestGuard() {
  const currentId = ref(0);

  function nextRequestId() {
    currentId.value += 1;
    return currentId.value;
  }

  function isStaleRequest(id) {
    return id !== currentId.value;
  }

  return { nextRequestId, isStaleRequest };
}
