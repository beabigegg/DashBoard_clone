// @vitest-environment jsdom
/**
 * production-achievement/App.vue — template wiring tests (TDD, rewrite for
 * production-achievement-overhaul IP-8).
 *
 * 4-mode button wiring (default lands on 當日); station single-select reuses
 * the existing fake-single-select idiom; range-only date inputs visible only
 * in 自訂區間 (OD-2); 設定 button navigates to /production-achievement-settings
 * (OD-7 persistence itself is composable-level, tested in
 * useProductionAchievement.test.ts — this file confirms the button wiring +
 * that a persisted prior state is honoured on mount); OD-11 KPI cards must
 * equal SUM(actual)/SUM(plan) over the SAME rendered rows, never an
 * independently re-aggregated number.
 *
 * DuckDB is mocked at the `core/duckdb-client` + `core/duckdb-activation-policy`
 * boundary (same convention as before) so the REAL composable + App.vue
 * template run end-to-end. Only the genuinely HEAVY children (ECharts-backed
 * chart, DataTable, TargetEditPanel) are stubbed via targeted `global.stubs`
 * — SummaryCard/SummaryCardGroup stay real so their `props`/values are
 * inspectable (a blanket `shallow: true` stub renders as a childless void
 * element in this Vue Test Utils version, hiding nested SummaryCard props).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import App from '../App.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';

const navigateMock = vi.fn();
vi.mock('../../core/shell-navigation', () => ({
  navigateToRuntimeRoute: (...args: unknown[]) => navigateMock(...args),
}));

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
    targets_map: [],
    package_lf_map: [],
    workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB' }],
    daily_plan_map: [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 400 }],
  },
  meta: {},
};

const DAILY_ROWS = [
  { package_lf_group: 'SOD-123FL', d_output_qty: 200, n_output_qty: 100, daily_output_qty: 300, daily_plan_qty: 400, achievement_rate: 0.75 },
  { package_lf_group: 'TO-277(B)', d_output_qty: 50, n_output_qty: 50, daily_output_qty: 100, daily_plan_qty: 100, achievement_rate: 1.0 },
];

async function getDuckClient() {
  return (await import('../../core/duckdb-client')).getDuckDBClient() as unknown as {
    init: ReturnType<typeof vi.fn>;
    registerParquet: ReturnType<typeof vi.fn>;
    sendQuery: ReturnType<typeof vi.fn>;
    destroy: ReturnType<typeof vi.fn>;
  };
}

/** Stub only the genuinely heavy children (ECharts chart, DataTable internals,
 *  TargetEditPanel's own DataTable) — everything else (SummaryCard, MultiSelect,
 *  ErrorBanner, AsyncQueryProgress) renders for real so props/attrs are inspectable. */
function mountApp() {
  return mount(App, {
    attachTo: document.body,
    global: {
      stubs: {
        PlanAchievementStackedChart: true,
        DataTable: true,
        DataTableColumn: true,
        TargetEditPanel: true,
      },
    },
  });
}

describe('production-achievement App.vue', () => {
  const originalFetch = global.fetch;

  beforeEach(async () => {
    sessionStorage.clear();
    navigateMock.mockClear();
    global.fetch = vi.fn().mockResolvedValue(
      jsonResponse({ success: true, data: { shift_codes: ['N', 'D'], workcenter_groups: ['焊接_DB', '焊接_WB'] }, meta: {} }),
    );
    const client = await getDuckClient();
    client.sendQuery.mockClear().mockResolvedValue([]);
    client.init.mockClear();
    client.registerParquet.mockClear();
    client.destroy.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('defaults to 當日 mode on landing (no persisted state)', async () => {
    const wrapper = mountApp();
    await flushPromises();

    const todayBtn = wrapper.find('[data-testid="pa-mode-today"]');
    expect(todayBtn.exists()).toBe(true);
    expect(todayBtn.attributes('aria-pressed')).toBe('true');
    wrapper.unmount();
  });

  it('renders all 4 mode buttons and switching modes updates the active button', async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-mode-today"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-mode-yesterday"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-mode-month"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-mode-range"]').exists()).toBe(true);

    await wrapper.find('[data-testid="pa-mode-month"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-mode-month"]').attributes('aria-pressed')).toBe('true');
    expect(wrapper.find('[data-testid="pa-mode-today"]').attributes('aria-pressed')).toBe('false');
    wrapper.unmount();
  });

  it('range date inputs are visible ONLY in 自訂區間 mode', async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-range-start"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-range-end"]').exists()).toBe(false);

    await wrapper.find('[data-testid="pa-mode-range"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-range-start"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-range-end"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it('there is no 查詢/清除篩選 button (deleted controls — OD-3, auto-run)', async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-query-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-clear-filters"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('there is no shift-code filter control (OD-1)', async () => {
    const wrapper = mountApp();
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-shift-code"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('設定 button navigates to /production-achievement-settings', async () => {
    const wrapper = mountApp();
    await flushPromises();

    await wrapper.find('[data-testid="pa-settings-btn"]').trigger('click');
    expect(navigateMock).toHaveBeenCalledWith('/production-achievement-settings');
    wrapper.unmount();
  });

  it('OD-7: a persisted prior mode/station (simulating return from settings) is honoured on mount, not reset to defaults', async () => {
    sessionStorage.setItem('production-achievement:last-report-state', JSON.stringify({ mode: 'month', workcenter_group: '焊接_WB' }));

    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-mode-month"]').attributes('aria-pressed')).toBe('true');
    wrapper.unmount();
  });

  it('renders the daily table + reduced KPI cards after a successful today-mode query', async () => {
    const client = await getDuckClient();
    client.sendQuery
      .mockResolvedValueOnce([]) // spec map
      .mockResolvedValueOnce([]) // targets map
      .mockResolvedValueOnce([]) // package_lf map
      .mockResolvedValueOnce([]) // workcenter_merge map
      .mockResolvedValueOnce([]) // daily_plan map
      .mockResolvedValueOnce([]) // rollup_raw create
      .mockResolvedValueOnce([]) // rollup create
      .mockResolvedValueOnce(DAILY_ROWS); // computeDailyView SELECT

    // onMounted() fires fetchFilterOptions()/fetchTargets()/runQuery() as 3
    // independent (not sequentially-awaited) async chains — branch by URL
    // rather than relying on their relative fetch() arrival order.
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/filter-options')) {
        return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
      }
      if (u.includes('/api/production-achievement/targets')) {
        return Promise.resolve(jsonResponse({ success: true, data: [], meta: {} }));
      }
      if (u.includes('/api/production-achievement/report')) {
        return Promise.resolve(jsonResponse(SPOOL_HIT_BODY));
      }
      return Promise.resolve(jsonResponse({ success: true, data: {}, meta: {} }));
    });

    const wrapper = mountApp();
    await flushPromises();
    await flushPromises();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-report-table"]').exists()).toBe(true);

    // OD-11: KPI cards must equal SUM(actual)/SUM(plan) over the SAME two
    // rendered rows above — 300+100=400 actual, 400+100=500 plan, 400/500=0.8
    // — never an independently re-aggregated/re-derived number.
    expect(wrapper.find('[data-testid="pa-kpi-cards"]').exists()).toBe(true);
    const kpiCards = wrapper.findAllComponents(SummaryCard);
    const byLabel = Object.fromEntries(kpiCards.map((c) => [c.props('label'), c.props('value')]));
    expect(byLabel['實際產出合計']).toBe(400);
    expect(byLabel['計畫合計']).toBe(500);
    expect(byLabel['整體達成率']).toBeCloseTo(80.0, 5);
    wrapper.unmount();
  });

  it('hides results and shows ErrorBanner on a query failure (no contradictory empty table)', async () => {
    const wrapper = mountApp();
    await flushPromises();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      jsonResponse({ success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '背景查詢服務不可用，請稍後再試' }, meta: {} }, 503),
    );
    await wrapper.find('[data-testid="pa-mode-yesterday"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-report-table"]').exists()).toBe(false);
    const banner = wrapper.findComponent(ErrorBanner);
    expect(banner.props('message')).toContain('背景查詢服務不可用');
    wrapper.unmount();
  });
});
