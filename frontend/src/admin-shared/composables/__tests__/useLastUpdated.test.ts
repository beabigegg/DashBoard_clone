// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useLastUpdated } from '../useLastUpdated'

describe('useLastUpdated', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-19T09:30:45'))
  })
  afterEach(() => { vi.useRealTimers() })

  it('initial label is empty', () => {
    const { lastUpdatedLabel } = useLastUpdated()
    expect(lastUpdatedLabel.value).toBe('')
  })

  it('markUpdated sets label to HH:MM:SS format', () => {
    const { lastUpdatedLabel, markUpdated } = useLastUpdated()
    markUpdated()
    expect(lastUpdatedLabel.value).toBe('最後更新: 09:30:45')
  })

  it('calling markUpdated twice updates to latest time', () => {
    const { lastUpdatedLabel, markUpdated } = useLastUpdated()
    markUpdated()
    vi.setSystemTime(new Date('2026-05-19T10:00:00'))
    markUpdated()
    expect(lastUpdatedLabel.value).toBe('最後更新: 10:00:00')
  })
})
