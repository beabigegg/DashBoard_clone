// @vitest-environment jsdom
/**
 * production-achievement/App.vue — template wiring tests.
 *
 * FIX 1 (UX-1, monkey/UI-UX review follow-up on production-achievement-async
 * -spool): on a failed query (error truthy), the results section
 * (SummaryCardGroup/AchievementChart/the detail DataTable) must NOT render
 * alongside ErrorBanner — showing "service unavailable" AND a "no matching
 * data" empty table at the same time is contradictory. A genuine zero-row
 * *success* (no error) must still render the results section as-is (the
 * DataTable's own empty-type="filter-empty" state).
 *
 * DuckDB is mocked at the `core/duckdb-client` + `core/duckdb-activation-policy`
 * boundary (same convention as useProductionAchievement.test.ts) so the REAL
 * composable + App.vue template run end-to-end; `shallow: true` stubs heavy
 * child components (echarts-backed AchievementChart, DataTable internals) so
 * this stays a fast, focused structural test — presence/absence is asserted
 * via findComponent() against the real component modules, not the stub markup.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import App from '../App.vue';
import SummaryCardGroup from '../../shared-ui/components/SummaryCardGroup.vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import AchievementChart from '../components/AchievementChart.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';

vi.mock('../../core/duckdb-activation-policy', () => ({
  checkLocalComputeEligibility: vi.fn().mockReturnValue({ eligible: true, reason: 'ok' }),
}));

vi.mock('../../core/duckdb-client', () => {
  const mockClient = {
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    sendQuery: vi.fn().mockResolvedValue([]),
    destroy: vi.fn(),
  };
  return {
    getDuckDBClient: vi.fn().mockReturnValue(mockClient),
    fetchParquetBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)),
    isDuckDBSupported: vi.fn().mockReturnValue(true),
  };
});

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

const SPOOL_HIT_BODY = {
  success: true,
  data: {
    query_id: 'abc123',
    spool_download_url: '/api/spool/production_achievement/abc123.parquet',
    spec_workcenter_map: [{ SPECNAME: 'EPOXY D/B', workcenter_group: '焊接_DB' }],
    targets_map: [{ shift_code: 'D', workcenter_group: '焊接_DB', target_qty: 120 }],
  },
  meta: {},
};

const COMPUTED_ROW = {
  output_date: '2026-01-01',
  shift_code: 'D',
  workcenter_group: '焊接_DB',
  actual_output_qty: 100,
  target_qty: 120,
  achievement_rate: 0.833,
};

describe('production-achievement App.vue — error vs empty-result rendering (FIX 1)', () => {
  const originalFetch = global.fetch;

  beforeEach(async () => {
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ success: true, data: { shift_codes: ['N', 'D'], workcenter_groups: [] }, meta: {} }),
    );
    const client = await (await import('../../core/duckdb-client')).getDuckDBClient();
    (client.sendQuery as ReturnType<typeof vi.fn>).mockClear().mockResolvedValue([]);
    (client.init as ReturnType<typeof vi.fn>).mockClear();
    (client.registerParquet as ReturnType<typeof vi.fn>).mockClear();
    (client.destroy as ReturnType<typeof vi.fn>).mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('renders the results section after a successful query with rows', async () => {
    const wrapper = mount(App, { shallow: true, attachTo: document.body });
    await flushPromises(); // onMounted: fetchFilterOptions + fetchTargets

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));
    const client = await (await import('../../core/duckdb-client')).getDuckDBClient();
    (client.sendQuery as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([COMPUTED_ROW]);

    await wrapper.find('[data-testid="pa-query-btn"]').trigger('click');
    await flushPromises();

    expect(wrapper.findComponent(SummaryCardGroup).exists()).toBe(true);
    expect(wrapper.findComponent(AchievementChart).exists()).toBe(true);
    expect(wrapper.findComponent(DataTable).exists()).toBe(true);
    wrapper.unmount();
  });

  it('FIX 1: hides SummaryCardGroup/AchievementChart/DataTable on a 503 error — only ErrorBanner carries the message', async () => {
    const wrapper = mount(App, { shallow: true, attachTo: document.body });
    await flushPromises();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse(
        { success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '背景查詢服務不可用，請稍後再試' }, meta: {} },
        503,
      ),
    );

    await wrapper.find('[data-testid="pa-query-btn"]').trigger('click');
    await flushPromises();

    // The report DataTable specifically (SummaryCardGroup/AchievementChart
    // wrap only the "success" branch alongside it) must not render.
    expect(wrapper.find('[data-testid="pa-report-table"]').exists()).toBe(false);
    expect(wrapper.findComponent(SummaryCardGroup).exists()).toBe(false);
    expect(wrapper.findComponent(AchievementChart).exists()).toBe(false);
    expect(wrapper.findComponent(DataTable).exists()).toBe(false);

    const banner = wrapper.findComponent(ErrorBanner);
    expect(banner.exists()).toBe(true);
    expect(banner.props('message')).toContain('背景查詢服務不可用');
    wrapper.unmount();
  });

  it('still renders the results section (empty table, not an error) for a genuine zero-row success', async () => {
    const wrapper = mount(App, { shallow: true, attachTo: document.body });
    await flushPromises();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(jsonResponse(SPOOL_HIT_BODY));
    const client = await (await import('../../core/duckdb-client')).getDuckDBClient();
    (client.sendQuery as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([]); // computeView SELECT -> zero rows, success

    await wrapper.find('[data-testid="pa-query-btn"]').trigger('click');
    await flushPromises();

    expect(wrapper.findComponent(ErrorBanner).props('message')).toBe('');
    expect(wrapper.findComponent(DataTable).exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-report-table"]').exists()).toBe(true);
    wrapper.unmount();
  });
});
