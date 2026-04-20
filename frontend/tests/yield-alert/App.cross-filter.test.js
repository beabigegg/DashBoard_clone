// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, nextTick, ref } from 'vue';
import { shallowMount } from '@vue/test-utils';

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();
const replaceRuntimeHistoryMock = vi.fn();

const duckdbState = {
  isActive: ref(false),
  activate: vi.fn(async () => true),
  deactivate: vi.fn(),
  computeView: vi.fn(async () => ({})),
};

vi.mock('../../src/core/api.js', () => ({
  apiGet: apiGetMock,
  apiPost: apiPostMock,
}));

vi.mock('../../src/shared-composables/useAsyncJobPolling.js', () => ({
  pollJobUntilComplete: vi.fn(async () => true),
}));

vi.mock('../../src/yield-alert-center/useYieldAlertDuckDB.js', () => ({
  useYieldAlertDuckDB: () => duckdbState,
}));

vi.mock('../../src/core/duckdb-client.js', () => ({
  isDuckDBSupported: () => false,
}));

vi.mock('../../src/core/shell-navigation.js', () => ({
  replaceRuntimeHistory: replaceRuntimeHistoryMock,
}));

vi.mock('../../src/shared-composables/useFilterOrchestrator.js', () => ({
  useFilterOrchestrator: () => ({}),
}));

const MultiSelectStub = defineComponent({
  name: 'MultiSelect',
  props: {
    modelValue: { type: Array, default: () => [] },
    options: { type: Array, default: () => [] },
  },
  emits: ['update:modelValue'],
  template: '<div class="multi-select-stub">{{ (modelValue || []).join(",") }}</div>',
});

function buildViewPayload({ page = 1, perPage = 20, totalPages = 2 } = {}) {
  return {
    success: true,
    data: {
      summary: { transaction_qty: 100, scrap_qty: 1, yield_pct: 99 },
      trend: { items: [] },
      heatmap: { items: [] },
      station_summary: { items: [] },
      package_summary: { items: [] },
      alerts: {
        items: [
          {
            date_bucket: '2026-03-01',
            workorder: 'WO-001',
            reason_code: 'R001',
            department: '焊接_WB',
            package: 'PKG-A',
            type: 'TYPE-A',
            scrap_qty: 3,
            yield_pct: 97.5,
            risk_level: 'medium',
            risk_score: 77.5,
          },
        ],
        pagination: { page, per_page: perPage, total: totalPages * perPage, total_pages: totalPages },
      },
      filter_options: {
        lines: ['L1', 'L2'],
        packages: ['PKG-A', 'PKG-B'],
        types: ['TYPE-A'],
        functions: ['FUNC-A'],
      },
    },
  };
}

describe('Yield Alert App URL and cross-filter behavior', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();
    replaceRuntimeHistoryMock.mockReset();
    duckdbState.isActive.value = false;
    duckdbState.activate.mockClear();
    duckdbState.deactivate.mockClear();
    duckdbState.computeView.mockClear();
    vi.useFakeTimers();
  });

  it('restores legacy departments query param into workcenter group selection', async () => {
    window.history.replaceState({}, '', '/yield-alert-center?query_id=qid-legacy-001&start_date=2026-03-01&end_date=2026-03-07&departments=%E7%84%8A%E6%8E%A5_WB');

    apiGetMock.mockImplementation(async (url) => {
      if (url === '/api/yield-alert/filter-options') {
        return { success: true, data: { workcenter_groups: ['焊接_DB', '焊接_WB'] } };
      }
      return { success: true, data: {} };
    });

    const { default: YieldAlertApp } = await import('../../src/yield-alert-center/App.vue');

    const wrapper = shallowMount(YieldAlertApp, {
      global: {
        stubs: {
          MultiSelect: MultiSelectStub,
          EmptyState: true,
          ErrorBanner: true,
          LoadingOverlay: true,
          LoadingSpinner: true,
          PageHeader: true,
          SummaryCard: true,
          SummaryCardGroup: true,
          YieldHeatmap: true,
          YieldStationChart: true,
          YieldPackageChart: true,
          YieldTrendChart: true,
        },
      },
    });

    await nextTick();
    await nextTick();

    const dateInputs = wrapper.findAll('input[type="date"]');
    expect(dateInputs[0].element.value).toBe('2026-03-01');
    expect(dateInputs[1].element.value).toBe('2026-03-07');

    const selectTexts = wrapper.findAll('.multi-select-stub').map((node) => node.text());
    expect(selectTexts[0]).toBe('焊接_WB');
    expect(wrapper.text()).toContain('已建立快取: qid-legacy-001');
  });

  it('requests cross-filter options after supplementary filter changes on queried data', async () => {
    window.history.replaceState({}, '', '/yield-alert-center?query_id=qid-001&start_date=2026-03-01&end_date=2026-03-07');

    apiGetMock.mockImplementation(async (url) => {
      if (url === '/api/yield-alert/filter-options') {
        return { success: true, data: { workcenter_groups: ['焊接_WB'] } };
      }
      if (url === '/api/yield-alert/view') {
        throw new Error('unexpected direct view call signature');
      }
      if (url.startsWith('/api/yield-alert/cross-filter-options?')) {
        return {
          success: true,
          data: {
            lines: ['L1'],
            packages: ['PKG-A'],
            types: ['TYPE-A'],
            functions: ['FUNC-A'],
          },
        };
      }
      return { success: true, data: {} };
    });

    apiPostMock.mockResolvedValue({
      success: true,
      data: { query_id: 'qid-001' },
    });

    const { default: YieldAlertApp } = await import('../../src/yield-alert-center/App.vue');

    const wrapper = shallowMount(YieldAlertApp, {
      global: {
        stubs: {
          MultiSelect: MultiSelectStub,
          EmptyState: true,
          ErrorBanner: true,
          LoadingOverlay: true,
          LoadingSpinner: true,
          PageHeader: true,
          SummaryCard: true,
          SummaryCardGroup: true,
          YieldHeatmap: true,
          YieldStationChart: true,
          YieldPackageChart: true,
          YieldTrendChart: true,
        },
      },
    });

    apiGetMock.mockImplementation(async (url, options = {}) => {
      if (url === '/api/yield-alert/filter-options') {
        return { success: true, data: { workcenter_groups: ['焊接_WB'] } };
      }
      if (url === '/api/yield-alert/view') {
        expect(options.params).toMatchObject({
          query_id: 'qid-001',
          page: 1,
          per_page: 20,
        });
        return {
          success: true,
          data: {
            summary: { transaction_qty: 100, scrap_qty: 1, yield_pct: 99 },
            trend: { items: [] },
            heatmap: { items: [] },
            station_summary: { items: [] },
            package_summary: { items: [] },
            alerts: {
              items: [],
              pagination: { page: 1, per_page: 20, total: 0, total_pages: 1 },
            },
            filter_options: {
              lines: ['L1', 'L2'],
              packages: ['PKG-A', 'PKG-B'],
              types: ['TYPE-A'],
              functions: ['FUNC-A'],
            },
          },
        };
      }
      if (url.startsWith('/api/yield-alert/cross-filter-options?')) {
        return {
          success: true,
          data: {
            lines: ['L1'],
            packages: ['PKG-A'],
            types: ['TYPE-A'],
            functions: ['FUNC-A'],
          },
        };
      }
      return { success: true, data: {} };
    });

    await nextTick();
    await nextTick();

    const primaryButton = wrapper.find('button.ui-btn--primary');
    await primaryButton.trigger('click');
    await nextTick();
    await nextTick();

    const multiSelects = wrapper.findAllComponents(MultiSelectStub);
    expect(multiSelects.length).toBeGreaterThanOrEqual(2);

    await multiSelects[1].vm.$emit('update:modelValue', ['L1']);
    await nextTick();
    vi.advanceTimersByTime(350);
    await nextTick();

    const crossFilterCall = apiGetMock.mock.calls.find(([url]) => url.startsWith('/api/yield-alert/cross-filter-options?'));
    expect(crossFilterCall).toBeTruthy();
    expect(crossFilterCall[0]).toContain('query_id=qid-001');
    expect(crossFilterCall[0]).toContain('lines=L1');
  });

  it('restores sort and per-page from URL, then syncs sort and page changes back into runtime URL', async () => {
    window.history.replaceState(
      {},
      '',
      '/yield-alert-center?query_id=qid-002&start_date=2026-03-01&end_date=2026-03-07&per_page=50&sort_by=risk_score&sort_dir=asc&granularity=week',
    );

    apiPostMock.mockResolvedValue({
      success: true,
      data: { query_id: 'qid-002' },
    });

    apiGetMock.mockImplementation(async (url, options = {}) => {
      if (url === '/api/yield-alert/filter-options') {
        return { success: true, data: { workcenter_groups: ['焊接_WB'] } };
      }
      if (url === '/api/yield-alert/view') {
        if (options.params?.page === 1) {
          expect(options.params).toMatchObject({
            query_id: 'qid-002',
            page: 1,
            per_page: 50,
            sort_by: 'risk_score',
            sort_dir: 'asc',
            granularity: 'week',
          });
          return buildViewPayload({ page: 1, perPage: 50, totalPages: 3 });
        }

        if (options.params?.page === 2) {
          expect(options.params).toMatchObject({
            query_id: 'qid-002',
            page: 2,
            per_page: 50,
            sort_by: 'scrap_qty',
            sort_dir: 'asc',
            granularity: 'week',
          });
          return buildViewPayload({ page: 2, perPage: 50, totalPages: 3 });
        }
      }
      return { success: true, data: {} };
    });

    const { default: YieldAlertApp } = await import('../../src/yield-alert-center/App.vue');

    const wrapper = shallowMount(YieldAlertApp, {
      global: {
        stubs: {
          MultiSelect: MultiSelectStub,
          EmptyState: true,
          ErrorBanner: true,
          LoadingOverlay: true,
          LoadingSpinner: true,
          PageHeader: true,
          SummaryCard: true,
          SummaryCardGroup: true,
          YieldHeatmap: true,
          YieldStationChart: true,
          YieldPackageChart: true,
          YieldTrendChart: true,
        },
      },
    });

    await nextTick();
    await nextTick();

    const primaryButton = wrapper.find('button.ui-btn--primary');
    await primaryButton.trigger('click');
    await nextTick();
    await nextTick();

    const sortButtons = wrapper.findAll('button.th-btn');
    expect(sortButtons.length).toBe(3);
    await sortButtons[0].trigger('click');
    await nextTick();
    await nextTick();

    const nextPageButton = wrapper.findAll('footer.pagination button').at(1);
    expect(nextPageButton?.text()).toContain('下一頁');
    await nextPageButton.trigger('click');
    await nextTick();
    await nextTick();

    const latestUrl = replaceRuntimeHistoryMock.mock.calls.at(-1)?.[0] || '';
    expect(latestUrl).toContain('query_id=qid-002');
    expect(latestUrl).toContain('per_page=50');
    expect(latestUrl).toContain('sort_by=scrap_qty');
    expect(latestUrl).toContain('sort_dir=asc');
    expect(latestUrl).toContain('granularity=week');
    expect(latestUrl).toContain('page=2');
  });
});
