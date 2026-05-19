import { ref, type Ref } from 'vue'

export function useLastUpdated(): { lastUpdatedLabel: Ref<string>; markUpdated: () => void } {
  const lastUpdatedLabel = ref('')

  function markUpdated(): void {
    const d = new Date()
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    lastUpdatedLabel.value = `最後更新: ${hh}:${mm}:${ss}`
  }

  return { lastUpdatedLabel, markUpdated }
}
