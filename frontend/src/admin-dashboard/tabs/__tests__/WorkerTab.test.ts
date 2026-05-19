// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('vue-echarts', () => ({
  default: defineComponent({ name: 'VChart', props: ['option', 'autoresize'], template: '<canvas />' }),
}))
vi.mock('../../../admin-shared/components/GaugeBar.vue', () => ({
  default: defineComponent({ name: 'GaugeBar', props: ['label', 'value', 'max', 'displayText', 'warningThreshold', 'dangerThreshold'], template: '<div class="gauge-bar-stub" />' }),
}))
vi.mock('../../../admin-shared/components/StatCard.vue', () => ({
  default: defineComponent({ name: 'StatCard', props: ['value', 'label'], template: '<div class="stat-card-stub" />' }),
}))
vi.mock('../../../admin-shared/components/StatusDot.vue', () => ({
  default: defineComponent({ name: 'StatusDot', props: ['status', 'label'], template: '<span />' }),
}))
vi.mock('../../../shared-ui/components/ErrorBanner.vue', () => ({
  default: defineComponent({ name: 'ErrorBanner', props: ['message', 'dismissible'], template: '<div class="error-banner-stub" />' }),
}))
vi.mock('../../../shared-ui/components/DataTable.vue', () => ({
  default: defineComponent({ name: 'DataTable', props: ['data', 'loading', 'pagination'], template: '<div class="data-table-stub"><slot /></div>' }),
}))
vi.mock('../../../shared-ui/components/DataTableColumn.vue', () => ({
  default: defineComponent({ name: 'DataTableColumn', props: ['columnKey', 'label', 'align'], template: '<div />' }),
}))
vi.mock('../../core/api.js', () => ({
  apiGet: async () => ({ data: null }),
  apiPost: async () => ({ data: null }),
}))
vi.mock('../../core/datetime.js', () => ({
  formatLogTime: (v: unknown) => String(v ?? ''),
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
  }
})

// @ts-expect-error — JS SFC
import WorkerTab from '../WorkerTab.vue'

const WORKER_PAYLOAD = {
  worker_memory_guard: {
    enabled: true,
    process_memory: {
      rss_mb: 120.5,
      limit_mb: 512,
      rss_pct: 23.5,
      level: 'normal',
      warn_count: 0,
      evict_count: 0,
      restart_count: 0,
    },
    service_memory: { rss_mb: 350.0, process_count: 3, gunicorn_rss_mb: 200.0, rq_rss_mb: 100.0 },
    system_memory: { used_pct: 45.0, used_mb: 7200, total_mb: 16000, available_mb: 8800, pressure_state: 'normal' },
  },
  async_workers: {
    rq_available: true,
    workers: { summary: { total: 2, busy: 0 }, workers: [] },
    queues: { total_queued: 0, total_failed: 0, queues: [] },
    slots: { active: 1, max: 4, utilization_pct: 25 },
  },
}

function mountWorker(payload = WORKER_PAYLOAD) {
  mockStore.perfDetailData = payload
  mockStore.historyData = []
  return mount(WorkerTab, { attachTo: document.body })
}

describe('WorkerTab — admin-dashboard-ux', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-19T09:30:45'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('all_trend_charts_render_after_memory_guard_section', async () => {
    const w = mountWorker()
    await w.vm.$nextTick()
    const html = w.html()
    const memGuardPos = html.indexOf('記憶體守衛')
    const trendPos = html.indexOf('trend-chart-card')
    // trend charts should appear after the memory guard section header
    expect(memGuardPos).toBeGreaterThanOrEqual(0)
    expect(trendPos).toBeGreaterThan(memGuardPos)
  })

  it('all_trend_charts_render_after_async_workers_section', async () => {
    const w = mountWorker()
    await w.vm.$nextTick()
    const html = w.html()
    const asyncPos = html.indexOf('非同步查詢 Worker')
    const trendPos = html.indexOf('trend-chart-card')
    expect(asyncPos).toBeGreaterThanOrEqual(0)
    expect(trendPos).toBeGreaterThan(asyncPos)
  })

  it('all_trend_charts_render_after_worker_control_section', async () => {
    const w = mountWorker()
    await w.vm.$nextTick()
    const html = w.html()
    const controlPos = html.indexOf('Worker 控制')
    const trendPos = html.lastIndexOf('trend-chart-card')
    expect(controlPos).toBeGreaterThanOrEqual(0)
    expect(trendPos).toBeGreaterThan(controlPos)
  })

  it('last_updated_label_updates_to_new_time_after_refresh', async () => {
    const w = mountWorker()
    await w.vm.$nextTick()
    await (w.vm as unknown as { refresh: () => Promise<void> }).refresh()
    await w.vm.$nextTick()
    expect(w.find('.admin-tab__last-updated').text()).toBe('最後更新: 09:30:45')
  })
})
