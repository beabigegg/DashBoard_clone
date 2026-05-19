// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('../../../admin-shared/components/GaugeBar.vue', () => ({
  default: defineComponent({ name: 'GaugeBar', props: ['label', 'value', 'max', 'displayText', 'warningThreshold', 'dangerThreshold'], template: '<div class="gauge-bar-stub" />' }),
}))
vi.mock('../../../admin-shared/components/TrendChart.vue', () => ({
  default: defineComponent({ name: 'TrendChart', props: ['snapshots', 'series', 'title', 'yAxisLabel', 'yMax'], template: '<div class="trend-chart-stub" />' }),
}))
vi.mock('../../../admin-shared/components/StatCard.vue', () => ({
  default: defineComponent({ name: 'StatCard', template: '<div />' }),
}))
vi.mock('../../../shared-ui/components/ErrorBanner.vue', () => ({
  default: defineComponent({ name: 'ErrorBanner', props: ['message', 'dismissible'], template: '<div class="error-banner-stub" />' }),
}))
vi.mock('../../../shared-ui/components/DataTable.vue', () => ({
  default: defineComponent({ name: 'DataTable', props: ['data', 'loading'], template: '<div class="data-table-stub"><slot /></div>' }),
}))
vi.mock('../../../shared-ui/components/DataTableColumn.vue', () => ({
  default: defineComponent({ name: 'DataTableColumn', props: ['columnKey', 'label', 'align'], template: '<div />' }),
}))

const { mockStore } = vi.hoisted(() => ({
  mockStore: {
    perfDetailData: null as unknown,
    historyData: [] as unknown[],
  },
}))

vi.mock('../../../admin-shared/composables/useAdminData', async () => {
  const { ref: vRef } = await import('vue')
  return {
    usePerfDetail: () => ({
      data: vRef(mockStore.perfDetailData),
      loading: vRef(false),
      error: vRef(''),
      refresh: async () => null,
    }),
    usePerfHistory: () => ({
      data: vRef(mockStore.historyData),
      loading: vRef(false),
      error: vRef(''),
      refresh: async () => null,
    }),
    useMetrics: () => ({
      data: vRef(null),
      loading: vRef(false),
      error: vRef(''),
      refresh: async () => null,
    }),
  }
})

// @ts-expect-error — JS SFC
import CacheTab from '../CacheTab.vue'
// @ts-expect-error — JS SFC
import PerformanceTab from '../PerformanceTab.vue'

const REDIS_BASE = {
  used_memory: 10_000_000,
  used_memory_human: '9.54 MB',
  peak_memory: 12_000_000,
  peak_memory_human: '11.44 MB',
  maxmemory: 0,
  maxmemory_human: '0B',
  connected_clients: 3,
  hit_rate: 0.87,
  namespaces: [],
}

function makePayload(overrides: Record<string, unknown> = {}) {
  return {
    redis: {
      ...REDIS_BASE,
      evicted_keys: 0,
      expired_keys: 0,
      mem_fragmentation_ratio: 1.0,
      slowlog: [],
    },
    process_caches: {},
    ...overrides,
  }
}

function mountCache(payload: unknown) {
  mockStore.perfDetailData = payload
  return mount(CacheTab, { attachTo: document.body })
}

function mountPerf(payload: unknown) {
  mockStore.perfDetailData = payload
  return mount(PerformanceTab, { attachTo: document.body })
}

describe('CacheTab slowlog duration formatting (AC-5)', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('slowlog_duration_999us_renders_microsecond_suffix', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [{ id: 1, duration_us: 999, command: 'GET foo' }] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    expect(w.text()).toContain('999μs')
  })

  it('slowlog_duration_1000us_renders_millisecond_suffix', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [{ id: 1, duration_us: 1000, command: 'GET foo' }] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    expect(w.text()).toContain('1.0ms')
  })

  it('slowlog_duration_999999us_renders_millisecond_suffix', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [{ id: 1, duration_us: 999_999, command: 'GET foo' }] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    expect(w.text()).toContain('1000.0ms')
  })

  it('slowlog_duration_1000000us_renders_second_suffix', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [{ id: 1, duration_us: 1_000_000, command: 'GET foo' }] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    expect(w.text()).toContain('1.0s')
  })

  it('slowlog_duration_large_renders_second_suffix_no_us_or_ms', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [{ id: 1, duration_us: 5_000_000, command: 'GET foo' }] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    expect(w.text()).toContain('5.0s')
    expect(w.text()).not.toContain('5000000μs')
    expect(w.text()).not.toContain('5000.0ms')
  })
})

describe('CacheTab threshold wiring (AC-4)', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('mem_fragmentation_ratio_1_5_triggers_warning_accent', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.5, slowlog: [] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    const cards = w.findAll('[data-accent]')
    const fragCard = cards.find((c) => c.text().includes('1.50'))
    expect(fragCard?.attributes('data-accent')).toBe('warning')
  })

  it('mem_fragmentation_ratio_2_0_triggers_danger_accent', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 2.0, slowlog: [] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    const cards = w.findAll('[data-accent]')
    const fragCard = cards.find((c) => c.text().includes('2.00'))
    expect(fragCard?.attributes('data-accent')).toBe('danger')
  })

  it('mem_fragmentation_ratio_1_49_uses_static_accent', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.49, slowlog: [] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    const cards = w.findAll('[data-accent]')
    const fragCard = cards.find((c) => c.text().includes('1.49'))
    expect(fragCard?.attributes('data-accent')).toBe('info')
  })

  it('evicted_keys_1_triggers_warning_accent', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 1, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    const cards = w.findAll('[data-accent]')
    // The evicted_keys card shows value "1" and has warningThreshold=1, so at or above → warning
    // But the static accent is "danger", and warningThreshold=1 fires first before danger
    // Implementation: warningThreshold fires → 'warning' (but static accent is 'danger' + warningThreshold=1)
    // Since warning threshold is set, value=1 >= 1 → 'warning' (warning takes over from static 'danger')
    const evictCard = cards.find((c) => c.text() === '1' && c.classes().length === 0)
    // Find card that is the evicted_keys card - it shows the label 逐出鍵數
    // We need to find the summary-card containing the evicted keys value
    // The label is in summary-card__label, value in summary-card__value
    // Since the card renders warning threshold over the static accent, data-accent should be 'warning'
    const allCards = w.findAll('.summary-card')
    const evictedCard = allCards.find((c) => c.text().includes('逐出鍵數'))
    expect(evictedCard?.attributes('data-accent')).toBe('warning')
  })

  it('evicted_keys_0_uses_static_accent', async () => {
    const payload = makePayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [] },
    })
    const w = mountCache(payload)
    await w.vm.$nextTick()
    const allCards = w.findAll('.summary-card')
    const evictedCard = allCards.find((c) => c.text().includes('逐出鍵數'))
    expect(evictedCard?.attributes('data-accent')).toBe('danger')
  })

  it('duckdb_temp_bytes_524288000_triggers_warning_accent', async () => {
    const payload = {
      db_pool: null,
      redis: null,
      process_caches: {},
      duckdb: { temp_dir_bytes: 524_288_000, memory_limit_state: 'ok' },
    }
    const w = mountPerf(payload)
    await w.vm.$nextTick()
    const allCards = w.findAll('.summary-card')
    const tempCard = allCards.find((c) => c.text().includes('Temp 目錄大小'))
    expect(tempCard?.attributes('data-accent')).toBe('warning')
  })

  it('duckdb_temp_bytes_below_threshold_uses_static_accent', async () => {
    const payload = {
      db_pool: null,
      redis: null,
      process_caches: {},
      duckdb: { temp_dir_bytes: 100_000, memory_limit_state: 'ok' },
    }
    const w = mountPerf(payload)
    await w.vm.$nextTick()
    const allCards = w.findAll('.summary-card')
    const tempCard = allCards.find((c) => c.text().includes('Temp 目錄大小'))
    expect(tempCard?.attributes('data-accent')).toBe('info')
  })
})

describe('CacheTab last-updated (AC-6)', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-19T09:30:45'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('last_updated_label_updates_to_new_time_after_refresh', async () => {
    const w = mountCache(makePayload())
    await w.vm.$nextTick()
    await (w.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await w.vm.$nextTick()
    expect(w.find('.admin-tab__last-updated').text()).toBe('最後更新: 09:30:45')
  })
})
