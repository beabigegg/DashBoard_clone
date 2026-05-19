// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('vue-echarts', () => ({
  default: defineComponent({ name: 'VChart', props: ['option', 'autoresize'], template: '<canvas />' }),
}))

import TrendChart from '../TrendChart.vue'

describe('TrendChart empty state', () => {
  it('empty_state_zero_snapshots_shows_first_line', () => {
    const w = mount(TrendChart, { props: { snapshots: [] } })
    expect(w.text()).toContain('趨勢資料不足（需至少 2 筆快照）')
  })
  it('empty_state_zero_snapshots_shows_second_line', () => {
    const w = mount(TrendChart, { props: { snapshots: [] } })
    expect(w.text()).toContain('（每 30 秒自動收集一次）')
  })
  it('empty_state_one_snapshot_shows_both_lines', () => {
    const w = mount(TrendChart, { props: { snapshots: [{ ts: '2026-01-01T00:00:00Z' }] } })
    expect(w.text()).toContain('趨勢資料不足（需至少 2 筆快照）')
    expect(w.text()).toContain('（每 30 秒自動收集一次）')
  })
  it('two_snapshots_hides_empty_state_shows_canvas', () => {
    const s = [{ ts: '2026-01-01T00:00:00Z' }, { ts: '2026-01-01T00:00:30Z' }]
    const w = mount(TrendChart, { props: { snapshots: s, series: [{ name: 'A', key: 'a', color: '#f00' }] } })
    expect(w.find('.trend-chart-empty').exists()).toBe(false)
    expect(w.find('.trend-chart-canvas').exists()).toBe(true)
  })
  it('empty_state_second_line_is_separate_dom_node', () => {
    const w = mount(TrendChart, { props: { snapshots: [] } })
    expect(w.find('.trend-chart-empty__hint').exists()).toBe(true)
    expect(w.find('.trend-chart-empty__primary').exists()).toBe(true)
  })
})
