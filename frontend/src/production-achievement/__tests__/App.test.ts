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
 * chart, DataTable) are stubbed via targeted `global.stubs` —
 * SummaryCard/SummaryCardGroup stay real so their `props`/values are
 * inspectable (a blanket `shallow: true` stub renders as a childless void
 * element in this Vue Test Utils version, hiding nested SummaryCard props).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import App from '../App.vue';
import ErrorBanner from '../../shared-ui/components/ErrorBanner.vue';
import SummaryCard from '../../shared-ui/components/SummaryCard.vue';
import PlanAchievementStackedChart from '../components/PlanAchievementStackedChart.vue';

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
    workcenter_merge_map: [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', parent_group: '焊接_DB', plan_source_side: 'input' }],
    plan_map: [{ output_date: '2026-07-14', plan_package_group: 'SOD-123FL', planqty_input: 400, planqty_output: 350 }],
  },
  meta: {},
};

// PA-21: shift_plan_qty = CEIL(daily_plan_qty / 2); d_/n_achievement_rate =
// each shift's own actual / shift_plan_qty. Row 1 deliberately illustrates
// the fixed bug: the OLD (buggy) chart formula d_output_qty/daily_plan_qty
// would read 200/400=0.5, HALF of the correct 200/200=1.0.
const DAILY_ROWS = [
  { package_lf_group: 'SOD-123FL', d_output_qty: 200, n_output_qty: 100, daily_output_qty: 300, daily_plan_qty: 400, achievement_rate: 0.75, shift_plan_qty: 200, d_achievement_rate: 1.0, n_achievement_rate: 0.5 },
  { package_lf_group: 'TO-277(B)', d_output_qty: 50, n_output_qty: 50, daily_output_qty: 100, daily_plan_qty: 100, achievement_rate: 1.0, shift_plan_qty: 50, d_achievement_rate: 1.0, n_achievement_rate: 1.0 },
];

async function getDuckClient() {
  return (await import('../../core/duckdb-client')).getDuckDBClient() as unknown as {
    init: ReturnType<typeof vi.fn>;
    registerParquet: ReturnType<typeof vi.fn>;
    sendQuery: ReturnType<typeof vi.fn>;
    destroy: ReturnType<typeof vi.fn>;
  };
}

/** Stub only the genuinely heavy children (ECharts chart, DataTable internals)
 *  — everything else (SummaryCard, MultiSelect, ErrorBanner, AsyncQueryProgress)
 *  renders for real so props/attrs are inspectable. */
function mountApp() {
  return mount(App, {
    attachTo: document.body,
    global: {
      stubs: {
        PlanAchievementStackedChart: true,
        CumulativeTrendComboChart: true,
        DataTable: true,
        DataTableColumn: true,
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

  it('PA-18: renders the 產出/轉出 source TAB, defaults to 產出 active, and toggles on click', async () => {
    const wrapper = mountApp();
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-source-output"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-source-moveout"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-source-output"]').attributes('aria-pressed')).toBe('true');
    expect(wrapper.find('[data-testid="pa-source-moveout"]').attributes('aria-pressed')).toBe('false');

    await wrapper.find('[data-testid="pa-source-moveout"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-source-moveout"]').attributes('aria-pressed')).toBe('true');
    expect(wrapper.find('[data-testid="pa-source-moveout"]').classes()).toContain('pa-app__source-btn--active');
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

  it('the active mode button carries the glow-animation class, the inactive ones do not', async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-mode-today"]').classes()).toContain('pa-app__mode-btn--active');
    expect(wrapper.find('[data-testid="pa-mode-yesterday"]').classes()).not.toContain('pa-app__mode-btn--active');

    await wrapper.find('[data-testid="pa-mode-yesterday"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-mode-yesterday"]').classes()).toContain('pa-app__mode-btn--active');
    expect(wrapper.find('[data-testid="pa-mode-today"]').classes()).not.toContain('pa-app__mode-btn--active');
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

  it('設定 button navigates to /production-achievement-settings when whitelisted (PA-17)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/permissions/me')) {
        return Promise.resolve(jsonResponse({ success: true, data: { can_edit_targets: true }, meta: {} }));
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
    });

    const wrapper = mountApp();
    await flushPromises();

    await wrapper.find('[data-testid="pa-settings-btn"]').trigger('click');
    await flushPromises();
    expect(navigateMock).toHaveBeenCalledWith('/production-achievement-settings');
    wrapper.unmount();
  });

  it('設定 button is styled red (ui-btn--danger) regardless of permission (PA-17)', async () => {
    const wrapper = mountApp();
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-settings-btn"]').classes()).toContain('ui-btn--danger');
    wrapper.unmount();
  });

  it('設定 button blocks navigation and shows a message when NOT whitelisted (PA-17)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/permissions/me')) {
        return Promise.resolve(jsonResponse({ success: true, data: { can_edit_targets: false }, meta: {} }));
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
    });

    const wrapper = mountApp();
    await flushPromises();

    await wrapper.find('[data-testid="pa-settings-btn"]').trigger('click');
    await flushPromises();

    expect(navigateMock).not.toHaveBeenCalled();
    const banners = wrapper.findAllComponents(ErrorBanner);
    expect(banners.some((b) => (b.props('message') ?? '').includes('沒有權限'))).toBe(true);
    wrapper.unmount();
  });

  it('設定 button blocks navigation and shows a distinct message on a permission-check network failure (PA-17)', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/permissions/me')) {
        return Promise.reject(new Error('network down'));
      }
      return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
    });

    const wrapper = mountApp();
    await flushPromises();

    await wrapper.find('[data-testid="pa-settings-btn"]').trigger('click');
    await flushPromises();

    expect(navigateMock).not.toHaveBeenCalled();
    const banners = wrapper.findAllComponents(ErrorBanner);
    expect(banners.some((b) => (b.props('message') ?? '').includes('查詢失敗'))).toBe(true);
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

    // onMounted() fires fetchFilterOptions()/runQuery() as 2 independent (not
    // sequentially-awaited) async chains — branch by URL rather than relying
    // on their relative fetch() arrival order.
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/filter-options')) {
        return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
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
    expect(byLabel['實際產出合計 (K)']).toBe(400);
    expect(byLabel['計畫合計 (K)']).toBe(500);
    expect(byLabel['整體達成率']).toBeCloseTo(80.0, 5);
    wrapper.unmount();
  });

  it('PA-21: D/N shift chart series divide each shift by its OWN shift_plan_qty, never the full daily_plan_qty (regression for the fixed under-reporting bug)', async () => {
    const client = await getDuckClient();
    client.sendQuery
      .mockResolvedValueOnce([]) // spec map
      .mockResolvedValueOnce([]) // targets map
      .mockResolvedValueOnce([]) // package_lf map
      .mockResolvedValueOnce([]) // workcenter_merge map
      .mockResolvedValueOnce([]) // plan map
      .mockResolvedValueOnce([]) // rollup_raw create
      .mockResolvedValueOnce([]) // rollup create
      .mockResolvedValueOnce(DAILY_ROWS); // computeDailyView SELECT

    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/filter-options')) {
        return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
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

    const chart = wrapper.findComponent(PlanAchievementStackedChart);
    expect(chart.exists()).toBe(true);
    const series = chart.props('series') as { name: string; data: number[] }[];
    const dSeries = series.find((s) => s.name === 'D班')!;
    const nSeries = series.find((s) => s.name === 'N班')!;
    // Row 1 (SOD-123FL): d_achievement_rate=1.0, n_achievement_rate=0.5 — the
    // pre-fix formula (d_output_qty/daily_plan_qty = 200/400) would have read
    // 0.5 here instead of the correct 1.0.
    expect(dSeries.data[0]).toBeCloseTo(100.0, 5); // achievementRateForChart returns a percent
    expect(nSeries.data[0]).toBeCloseTo(50.0, 5);
    // Row 2 (TO-277(B)): both shifts hit exactly their per-shift target.
    expect(dSeries.data[1]).toBeCloseTo(100.0, 5);
    expect(nSeries.data[1]).toBeCloseTo(100.0, 5);
    wrapper.unmount();
  });

  it('PA-19: expanded 大項 (電鍍) KPI 實際合計 sums LEAF 子站 rows only — the 大項小計 rollup row is never double-counted', async () => {
    // Land directly on 電鍍 (轉出) so the initial auto-run renders expanded mode.
    sessionStorage.setItem(
      'production-achievement:last-report-state',
      JSON.stringify({ mode: 'today', source: 'moveout', workcenter_group: '電鍍' }),
    );
    const client = await getDuckClient();
    // GROUPING SETS output for the daily expand SELECT: 2 子站 leaves (no plan)
    // + 1 大項小計 (summed actuals + the parent-keyed plan). Every setup/CREATE
    // sendQuery returns []; only the expand daily SELECT gets the rows.
    client.sendQuery.mockImplementation((sql: string) => {
      const s = String(sql);
      if (s.includes('GROUPING SETS') && s.includes('achievement_rate')) {
        return Promise.resolve([
          { package_lf_group: 'PKG-1', workcenter_group: '掛鍍', is_subtotal: 0, d_output_qty: 200, n_output_qty: 100, daily_output_qty: 300, daily_plan_qty: null, achievement_rate: null },
          { package_lf_group: 'PKG-1', workcenter_group: '條鍍', is_subtotal: 0, d_output_qty: 60, n_output_qty: 40, daily_output_qty: 100, daily_plan_qty: null, achievement_rate: null },
          { package_lf_group: 'PKG-1', workcenter_group: null, is_subtotal: 1, d_output_qty: 260, n_output_qty: 140, daily_output_qty: 400, daily_plan_qty: 500, achievement_rate: 0.8 },
        ]);
      }
      return Promise.resolve([]);
    });

    const MOVEOUT_BODY = {
      success: true,
      data: {
        query_id: 'mv1',
        spool_download_url: '/api/spool/production_achievement_moveout/mv1.parquet',
        spec_workcenter_map: [],
        targets_map: [],
        package_lf_map: [],
        workcenter_merge_map: [
          { raw_workcenter_group: '掛鍍', merged_workcenter_group: '掛鍍', parent_group: '電鍍', plan_source_side: 'input' },
          { raw_workcenter_group: '條鍍', merged_workcenter_group: '條鍍', parent_group: '電鍍', plan_source_side: 'input' },
        ],
        plan_map: [{ output_date: '2026-07-14', plan_package_group: 'PKG-1', planqty_input: 500, planqty_output: 450 }],
        source: 'moveout',
      },
      meta: {},
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/filter-options')) {
        return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['電鍍', '焊接_DB'] }, meta: {} }));
      }
      if (u.includes('/api/production-achievement/report')) {
        return Promise.resolve(jsonResponse(MOVEOUT_BODY));
      }
      return Promise.resolve(jsonResponse({ success: true, data: {}, meta: {} }));
    });

    const wrapper = mountApp();
    await flushPromises();
    await flushPromises();
    await flushPromises();

    const kpiCards = wrapper.findAllComponents(SummaryCard);
    const byLabel = Object.fromEntries(kpiCards.map((c) => [c.props('label'), c.props('value')]));
    // LEAF sum only: 300 + 100 = 400 (NOT 800 with the 大項小計 double-counted).
    expect(byLabel['實際轉出合計 (K)']).toBe(400);
    // Only the 大項小計 row carries a plan, so 計畫合計 = its plan (no leaf plans).
    expect(byLabel['計畫合計 (K)']).toBe(500);
    expect(byLabel['整體達成率']).toBeCloseTo(80.0, 5);
    wrapper.unmount();
  });

  it('重新查詢 button is visible on 當日/前日/當月 but not on 自訂區間', async () => {
    const wrapper = mountApp();
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-refresh-btn"]').exists()).toBe(true); // 當日 (default)

    await wrapper.find('[data-testid="pa-mode-yesterday"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-refresh-btn"]').exists()).toBe(true);

    await wrapper.find('[data-testid="pa-mode-month"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-refresh-btn"]').exists()).toBe(true);

    await wrapper.find('[data-testid="pa-mode-range"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="pa-refresh-btn"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('clicking 重新查詢 unconditionally re-issues /report with force_refresh=true', async () => {
    const client = await getDuckClient();
    client.sendQuery.mockResolvedValue([]);

    const reportCalls: string[] = [];
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/production-achievement/filter-options')) {
        return Promise.resolve(jsonResponse({ success: true, data: { shift_codes: [], workcenter_groups: ['焊接_DB'] }, meta: {} }));
      }
      if (u.includes('/api/production-achievement/report')) {
        reportCalls.push(u);
        return Promise.resolve(jsonResponse(SPOOL_HIT_BODY));
      }
      return Promise.resolve(jsonResponse({ success: true, data: {}, meta: {} }));
    });

    const wrapper = mountApp();
    await flushPromises();
    await flushPromises();

    expect(reportCalls.length).toBeGreaterThan(0);
    expect(reportCalls[0]).not.toContain('force_refresh');

    await wrapper.find('[data-testid="pa-refresh-btn"]').trigger('click');
    await flushPromises();
    await flushPromises();

    const lastCall = reportCalls[reportCalls.length - 1];
    expect(lastCall).toContain('force_refresh=true');
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
    // A second ErrorBanner instance exists for the unrelated PA-17
    // settings-permission message (empty/hidden here) — find the one that
    // actually carries the query-failure text.
    const banners = wrapper.findAllComponents(ErrorBanner);
    const banner = banners.find((b) => (b.props('message') ?? '').includes('背景查詢服務不可用'));
    expect(banner).toBeTruthy();
    wrapper.unmount();
  });
});
