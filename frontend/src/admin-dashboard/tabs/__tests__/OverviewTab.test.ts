// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('../../../admin-shared/components/TrendChart.vue', () => ({
  default: defineComponent({ name: 'TrendChart', props: ['snapshots', 'series', 'title', 'yAxisLabel', 'yMax', 'height'], template: '<div class="trend-chart-stub" />' }),
}))
vi.mock('../../../admin-shared/components/StatusDot.vue', () => ({
  default: defineComponent({ name: 'StatusDot', props: ['status', 'label'], template: '<span />' }),
}))
vi.mock('../../../shared-ui/components/BlockLoadingState.vue', () => ({
  default: defineComponent({ name: 'BlockLoadingState', props: ['text'], template: '<div />' }),
}))
vi.mock('../../../shared-ui/components/ErrorBanner.vue', () => ({
  default: defineComponent({ name: 'ErrorBanner', props: ['message', 'dismissible'], template: '<div class="error-banner-stub" />' }),
}))

const { mockStore } = vi.hoisted(() => ({
  mockStore: {
    healthData: null as unknown,
    historyData: [] as unknown[],
  },
}))

vi.mock('../../../admin-shared/composables/useAdminData', async () => {
  const { ref: vRef } = await import('vue')
  return {
    useHealthSummary: () => ({
      data: vRef(mockStore.healthData),
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
  }
})

// @ts-expect-error — JS SFC
import OverviewTab from '../OverviewTab.vue'

const HEALTH_PAYLOAD = {
  services: { database: 'healthy', redis: 'healthy' },
  warnings: ['RQ Worker 離線', 'High memory'],
  async_workers: { rq_available: true, workers: { summary: { total: 2, busy: 0 } }, queues: { total_queued: 0, total_depth: 0 } },
  circuit_breaker: { state: 'CLOSED' },
  system_memory: { pressure: 'normal', used_pct: 40, total_mb: 16000, available_mb: 9600 },
  sync_worker: { running: true },
  anomaly_scheduler: { running: false },
  database_pool: { state: { saturation: 0.2 } },
}

function mountOverview(payload = HEALTH_PAYLOAD) {
  mockStore.healthData = payload
  mockStore.historyData = []
  return mount(OverviewTab, { attachTo: document.body })
}

describe('OverviewTab — admin-dashboard-ux', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-19T09:30:45'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('active_alerts_section_is_first_section_card_in_dom', async () => {
    const w = mountOverview()
    await w.vm.$nextTick()
    const sections = w.findAll('.shared-section-card')
    expect(sections.length).toBeGreaterThanOrEqual(1)
    // First section card should contain 系統警示
    expect(sections[0].text()).toContain('系統警示')
  })

  it('active_alerts_renders_before_status_grid', async () => {
    const w = mountOverview()
    await w.vm.$nextTick()
    const html = w.html()
    const alertsPos = html.indexOf('系統警示')
    const statusGridPos = html.indexOf('系統健康總覽')
    expect(alertsPos).toBeGreaterThanOrEqual(0)
    expect(statusGridPos).toBeGreaterThanOrEqual(0)
    expect(alertsPos).toBeLessThan(statusGridPos)
  })

  it('active_alerts_renders_before_trend_charts', async () => {
    const w = mountOverview()
    await w.vm.$nextTick()
    const html = w.html()
    const alertsPos = html.indexOf('系統警示')
    const trendPos = html.indexOf('30 分鐘趨勢')
    expect(alertsPos).toBeGreaterThanOrEqual(0)
    expect(trendPos).toBeGreaterThanOrEqual(0)
    expect(alertsPos).toBeLessThan(trendPos)
  })

  it('last_updated_label_present_after_mount', async () => {
    const w = mountOverview()
    await w.vm.$nextTick()
    // Initially empty string (no refresh called yet after vi.useFakeTimers)
    const label = w.find('.admin-tab__last-updated')
    expect(label.exists()).toBe(true)
  })

  it('last_updated_label_updates_to_new_time_after_refresh', async () => {
    const w = mountOverview()
    await w.vm.$nextTick()
    await (w.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await w.vm.$nextTick()
    expect(w.find('.admin-tab__last-updated').text()).toBe('最後更新: 09:30:45')
  })
})
