// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { formatDuration } from '../formatDuration'

describe('formatDuration', () => {
  it('999us renders microsecond suffix', () => expect(formatDuration(999)).toBe('999μs'))
  it('1000us renders millisecond suffix', () => expect(formatDuration(1000)).toBe('1.0ms'))
  it('999999us renders millisecond suffix', () => expect(formatDuration(999_999)).toBe('1000.0ms'))
  it('1000000us renders second suffix', () => expect(formatDuration(1_000_000)).toBe('1.0s'))
  it('large value renders seconds', () => expect(formatDuration(5_000_000)).toBe('5.0s'))
  it('null returns dash', () => expect(formatDuration(null)).toBe('-'))
  it('undefined returns dash', () => expect(formatDuration(undefined)).toBe('-'))
})
