// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SummaryCard from '../../../shared-ui/components/SummaryCard.vue'

describe('SummaryCard threshold props', () => {
  it('no_thresholds_uses_static_accent', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 5, accent: 'info' } })
    expect(w.attributes('data-accent')).toBe('info')
  })
  it('below_warning_uses_static_accent', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 1.2, accent: 'info', warningThreshold: 1.5 } })
    expect(w.attributes('data-accent')).toBe('info')
  })
  it('at_warning_threshold_renders_warning', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 1.5, accent: 'info', warningThreshold: 1.5 } })
    expect(w.attributes('data-accent')).toBe('warning')
  })
  it('above_warning_renders_warning', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 1.8, accent: 'info', warningThreshold: 1.5 } })
    expect(w.attributes('data-accent')).toBe('warning')
  })
  it('at_danger_threshold_renders_danger', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 2.0, accent: 'info', warningThreshold: 1.5, dangerThreshold: 2.0 } })
    expect(w.attributes('data-accent')).toBe('danger')
  })
  it('danger_takes_precedence_over_warning', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 2.5, accent: 'info', warningThreshold: 1.5, dangerThreshold: 2.0 } })
    expect(w.attributes('data-accent')).toBe('danger')
  })
  it('non_numeric_value_with_thresholds_falls_back_to_static_accent', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 'abc', accent: 'brand', warningThreshold: 1.5 } })
    expect(w.attributes('data-accent')).toBe('brand')
  })
  it('only_warning_threshold_no_danger_class', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: 0.5, accent: 'info', warningThreshold: 1.5 } })
    expect(w.attributes('data-accent')).not.toBe('danger')
  })
  it('thresholdValue_overrides_value_for_comparison', () => {
    const w = mount(SummaryCard, { props: { label: 'X', value: '512.0 MB', accent: 'info', thresholdValue: 600_000_000, warningThreshold: 524_288_000 } })
    expect(w.attributes('data-accent')).toBe('warning')
  })
})
