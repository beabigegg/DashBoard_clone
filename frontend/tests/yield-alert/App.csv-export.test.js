// @vitest-environment jsdom
/**
 * Regression coverage for yield-alert-kpi-csv-parity (IP-2 / AC-5).
 *
 * Symptom: `_buildAlertsCSV()` in `src/yield-alert-center/App.vue` writes
 * `toPcs(r.transaction_qty)` / `toPcs(r.scrap_qty)` straight into the CSV via
 * `String(v)` with no rounding. DuckDB DOUBLE SUM/ROUND leaves binary-float
 * residue (e.g. 4.0119999999999996 K-PCS), and `toPcs()` (*1000) amplifies it
 * into ugly values like `4011.9999999999995` in the exported CSV cell. Per
 * design.md Decision 4, the fix wraps `toPcs(...)` in `Math.round(...)` so the
 * CSV always contains a clean whole-pcs integer.
 *
 * `_buildAlertsCSV` is a private (non-exported) function inside App.vue's
 * `<script setup>`, so it is exercised indirectly here: mount the component,
 * restore a query from the URL, click "重新查詢日期範圍" (query-submit-btn) to
 * populate `alerts.value` via `/api/yield-alert/view`, then click "匯出全部
 * CSV" (which calls `exportAllAlertsCSV()` -> fetches
 * `/api/yield-alert/alerts` -> `_buildAlertsCSV()` -> `_triggerCSVDownload()`),
 * and capture the Blob content that would have been downloaded.
 *
 * MUST FAIL against current code: current code has no rounding, so the CSV
 * cell contains the raw float string, not the rounded integer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, nextTick } from 'vue';
import { shallowMount } from '@vue/test-utils';

const apiGetMock = vi.fn();
const apiPostMock = vi.fn();

vi.mock('../../src/core/api.js', () => ({
  apiGet: apiGetMock,
  apiPost: apiPostMock,
}));

vi.mock('../../src/shared-composables/useAsyncJobPolling.js', () => ({
  pollJobUntilComplete: vi.fn(async () => true),
}));

vi.mock('../../src/yield-alert-center/useYieldAlertDuckDB.js', () => ({
  useYieldAlertDuckDB: () => ({
    isActive: { value: false },
    activate: vi.fn(async () => true),
    deactivate: vi.fn(),
    computeView: vi.fn(async () => ({})),
  }),
}));

vi.mock('../../src/core/duckdb-client.js', () => ({
  isDuckDBSupported: () => false,
}));

vi.mock('../../src/core/shell-navigation.js', () => ({
  replaceRuntimeHistory: vi.fn(),
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

const GLOBAL_STUBS = {
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
};

// Vue's reactive DOM patch and the component's own apiGet-await chain both run
// as microtasks; a handful of nextTick() + microtask-flush rounds are needed
// to drain onMounted()'s async work and a click handler's awaited apiGet call.
async function flush(rounds = 15) {
  for (let i = 0; i < rounds; i++) {
    await nextTick();
    await Promise.resolve();
  }
}

// Raw K-PCS values whose *1000 conversion (toPcs) reproduces the exact
// binary-float residue reported in change-request.md: 4.0119999999999996 K-PCS
// -> 4011.9999999999995 pcs, and a companion scrap_qty value with the same
// class of residue (0.0509999999999999 K-PCS -> 50.9999999999999 pcs -> 51).
const FLOAT_NOISE_TRANSACTION_QTY = 4.0119999999999996;
const FLOAT_NOISE_SCRAP_QTY = 0.0509999999999999;

function buildViewPayload() {
  return {
    success: true,
    data: {
      summary: { transaction_qty: 4012, scrap_qty: 51, yield_pct: 98.7 },
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
            transaction_qty: FLOAT_NOISE_TRANSACTION_QTY,
            scrap_qty: FLOAT_NOISE_SCRAP_QTY,
            yield_pct: 98.7,
            risk_level: 'medium',
            risk_score: 12.34,
          },
        ],
        pagination: { page: 1, per_page: 20, total: 1, total_pages: 1 },
      },
      filter_options: {
        lines: ['L1'],
        packages: ['PKG-A'],
        types: ['TYPE-A'],
        functions: ['FUNC-A'],
      },
    },
  };
}

function buildAlertsPagePayload() {
  return {
    success: true,
    data: {
      items: [
        {
          date_bucket: '2026-03-01',
          workorder: 'WO-001',
          reason_code: 'R001',
          department: '焊接_WB',
          package: 'PKG-A',
          type: 'TYPE-A',
          transaction_qty: FLOAT_NOISE_TRANSACTION_QTY,
          scrap_qty: FLOAT_NOISE_SCRAP_QTY,
          yield_pct: 98.7,
          risk_level: 'medium',
          risk_score: 12.34,
        },
      ],
      pagination: { page: 1, per_page: 200, total: 1, total_pages: 1 },
    },
  };
}

function mockApiGet() {
  apiGetMock.mockImplementation(async (url) => {
    if (url === '/api/yield-alert/view') {
      return buildViewPayload();
    }
    if (url === '/api/yield-alert/alerts') {
      return buildAlertsPagePayload();
    }
    if (url === '/api/yield-alert/filter-options') {
      return { success: true, data: { workcenter_groups: ['焊接_WB'] } };
    }
    return { success: true, data: {} };
  });
}

async function mountQueriedApp(queryId) {
  window.history.replaceState(
    {},
    '',
    `/yield-alert-center?query_id=${queryId}&start_date=2026-03-01&end_date=2026-03-07`,
  );
  mockApiGet();

  const { default: YieldAlertApp } = await import('../../src/yield-alert-center/App.vue');
  const wrapper = shallowMount(YieldAlertApp, { global: { stubs: GLOBAL_STUBS } });
  await flush();

  // Populate alerts.value via the real /view fetch (query-submit-btn ->
  // runQuery(1) -> loadCachedView -> fetchViewPayload).
  await wrapper.find('[data-testid="query-submit-btn"]').trigger('click');
  await flush();

  return wrapper;
}

describe('Yield Alert App CSV export float-precision formatting', () => {
  let capturedBlobParts;
  let origCreateObjectURL;
  let origRevokeObjectURL;

  beforeEach(() => {
    apiGetMock.mockReset();
    apiPostMock.mockReset();

    capturedBlobParts = [];
    const OrigBlob = globalThis.Blob;
    globalThis.Blob = class MockBlob extends OrigBlob {
      constructor(parts, options) {
        super(parts, options);
        capturedBlobParts.push([...parts]);
      }
    };

    origCreateObjectURL = globalThis.URL.createObjectURL;
    origRevokeObjectURL = globalThis.URL.revokeObjectURL;
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock');
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    globalThis.URL.createObjectURL = origCreateObjectURL;
    globalThis.URL.revokeObjectURL = origRevokeObjectURL;
    vi.restoreAllMocks();
  });

  it('builds_alerts_csv_reproduces_and_fixes_duckdb_float_residue_case', async () => {
    const wrapper = await mountQueriedApp('qid-csv-001');

    const exportButton = wrapper.find('.btn-export-csv');
    expect(exportButton.exists()).toBe(true);
    expect(exportButton.attributes('disabled')).toBeFalsy();

    await exportButton.trigger('click');
    await flush();

    expect(capturedBlobParts.length).toBeGreaterThan(0);
    const csvContent = capturedBlobParts[capturedBlobParts.length - 1][0];
    const dataLine = csvContent.split('\n')[1];

    // Current (buggy) behavior would embed the raw float string, e.g.
    // "4011.9999999999995" — assert that noise is ABSENT.
    expect(dataLine).not.toContain('4011.9999999999995');
    expect(dataLine).not.toContain('.999999');
    expect(dataLine).not.toContain('.000000');

    // Expected (fixed) behavior: Math.round(toPcs(v)) -> clean whole-pcs
    // integers embedded in the quoted CSV cell.
    expect(dataLine).toContain('"4012"');
    expect(dataLine).toContain('"51"');
  });

  it('builds_alerts_csv_rounds_transaction_qty_and_scrap_qty_to_whole_pcs', async () => {
    const wrapper = await mountQueriedApp('qid-csv-002');

    await wrapper.find('.btn-export-csv').trigger('click');
    await flush();

    const csvContent = capturedBlobParts[capturedBlobParts.length - 1][0];
    const dataLine = csvContent.split('\n')[1];
    const cells = dataLine.split(',');

    // Column order per _buildAlertsCSV: date, workorder, LOT(source_code),
    // reason_code, department, package, type, transaction_qty(pcs),
    // scrap_qty(pcs), yield_pct, risk_level, risk_score
    const transactionQtyCell = cells[7];
    const scrapQtyCell = cells[8];

    // Every character inside the quotes must be a plain integer — no decimal
    // point, no scientific notation, no long float tail.
    expect(transactionQtyCell).toMatch(/^"\d+"$/);
    expect(scrapQtyCell).toMatch(/^"\d+"$/);
  });
});
