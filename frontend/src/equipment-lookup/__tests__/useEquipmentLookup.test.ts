// @vitest-environment jsdom
/**
 * Unit tests for useEquipmentLookup composable (equipment-lookup / 機台查詢)
 *
 * Covers: options load, filtered list query (each axis independently, incl.
 * one axis empty while a sibling is populated), server-side sort round-trip,
 * pagination, reset, and the client-side CSV export path (no dedicated
 * backend export endpoint — re-fetches page_size=10000 and downloads a blob).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../core/api', () => ({
  apiGet: vi.fn(),
}));

import { apiGet } from '../../core/api';
import { useEquipmentLookup, buildEquipmentCsv } from '../composables/useEquipmentLookup';

const mockApiGet = vi.mocked(apiGet);

function mockOptionsResponse() {
  return {
    success: true as const,
    data: {
      locations: ['LOC-A', 'LOC-B'],
      families: ['FAM-A'],
      resource_names: ['R001', 'R002'],
    },
  };
}

function mockListResponse(overrides: Record<string, unknown> = {}) {
  return {
    success: true as const,
    data: {
      rows: [
        {
          RESOURCENAME: 'R001',
          LOCATIONNAME: 'LOC-A',
          RESOURCEFAMILYNAME: 'FAM-A',
          VENDORNAME: 'Vendor1',
          VENDORMODEL: 'ModelX',
          WORKCENTERNAME: 'WC1',
        },
      ],
      pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 },
      ...overrides,
    },
  };
}

describe('useEquipmentLookup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (global as unknown as { URL: typeof URL }).URL.createObjectURL = vi.fn(() => 'blob:mock-url');
    (global as unknown as { URL: typeof URL }).URL.revokeObjectURL = vi.fn();
  });

  it('loads_filter_options', async () => {
    mockApiGet.mockResolvedValueOnce(mockOptionsResponse());
    const lookup = useEquipmentLookup();

    await lookup.loadOptions();

    expect(mockApiGet).toHaveBeenCalledWith('/api/equipment-lookup/options', expect.any(Object));
    expect(lookup.options.value.locations).toEqual(['LOC-A', 'LOC-B']);
    expect(lookup.options.value.families).toEqual(['FAM-A']);
    expect(lookup.options.value.resource_names).toEqual(['R001', 'R002']);
    expect(lookup.optionsError.value).toBe('');
  });

  it('options_load_error_sets_message', async () => {
    mockApiGet.mockResolvedValueOnce({ success: false, error: { message: '服務異常' } });
    const lookup = useEquipmentLookup();

    await lookup.loadOptions();

    expect(lookup.optionsError.value).toBe('服務異常');
  });

  it('submits_query_with_only_locations_selected', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();

    await lookup.submitQuery({ locations: ['LOC-A'], families: [], resource_names: [] });

    expect(lookup.hasQueried.value).toBe(true);
    const [, callOptions] = mockApiGet.mock.calls[0];
    const params = (callOptions as { params: Record<string, unknown> }).params;
    expect(params.locations).toEqual(['LOC-A']);
    expect(params.families).toEqual([]);
    expect(params.resource_names).toEqual([]);
    expect(lookup.rows.value).toHaveLength(1);
    expect(lookup.pagination.value.total).toBe(1);
  });

  it('submits_query_with_only_families_selected_locations_empty', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();

    await lookup.submitQuery({ locations: [], families: ['FAM-A'], resource_names: [] });

    const params = (mockApiGet.mock.calls[0][1] as { params: Record<string, unknown> }).params;
    expect(params.families).toEqual(['FAM-A']);
    expect(params.locations).toEqual([]);
  });

  it('submits_query_with_only_resource_names_selected', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();

    await lookup.submitQuery({ locations: [], families: [], resource_names: ['R001'] });

    const params = (mockApiGet.mock.calls[0][1] as { params: Record<string, unknown> }).params;
    expect(params.resource_names).toEqual(['R001']);
  });

  it('resets_sort_and_page_to_defaults_on_new_query', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();

    await lookup.submitQuery({ locations: [], families: [], resource_names: [] });

    const params = (mockApiGet.mock.calls[0][1] as { params: Record<string, unknown> }).params;
    expect(params.sort_by).toBe('RESOURCENAME');
    expect(params.sort_dir).toBe('asc');
    expect(params.page).toBe(1);
  });

  it('handles_empty_result', async () => {
    mockApiGet.mockResolvedValueOnce(
      mockListResponse({ rows: [], pagination: { page: 1, page_size: 20, total: 0, total_pages: 1 } })
    );
    const lookup = useEquipmentLookup();

    await lookup.submitQuery({ locations: [], families: [], resource_names: [] });

    expect(lookup.rows.value).toHaveLength(0);
    expect(lookup.pagination.value.total).toBe(0);
  });

  it('handleSort_re-fetches_page_1_with_new_sort', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();
    await lookup.submitQuery({ locations: [], families: [], resource_names: [] });

    mockApiGet.mockResolvedValueOnce(mockListResponse());
    await lookup.handleSort({ key: 'LOCATIONNAME', direction: 'desc' });

    const params = (mockApiGet.mock.calls[1][1] as { params: Record<string, unknown> }).params;
    expect(params.sort_by).toBe('LOCATIONNAME');
    expect(params.sort_dir).toBe('desc');
    expect(params.page).toBe(1);
    expect(lookup.activeSortBy.value).toBe('LOCATIONNAME');
    expect(lookup.activeSortDir.value).toBe('desc');
  });

  it('handlePageChange_preserves_current_filters_and_sort', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();
    await lookup.submitQuery({ locations: ['LOC-A'], families: [], resource_names: [] });

    mockApiGet.mockResolvedValueOnce(
      mockListResponse({ pagination: { page: 2, page_size: 20, total: 30, total_pages: 2 } })
    );
    await lookup.handlePageChange(2);

    const params = (mockApiGet.mock.calls[1][1] as { params: Record<string, unknown> }).params;
    expect(params.page).toBe(2);
    expect(params.locations).toEqual(['LOC-A']);
    expect(lookup.pagination.value.page).toBe(2);
  });

  it('reset_clears_query_state', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();
    await lookup.submitQuery({ locations: ['LOC-A'], families: [], resource_names: [] });
    expect(lookup.hasQueried.value).toBe(true);

    lookup.reset();

    expect(lookup.hasQueried.value).toBe(false);
    expect(lookup.rows.value).toHaveLength(0);
    expect(lookup.pagination.value.total).toBe(0);
    expect(lookup.activeSortBy.value).toBe('RESOURCENAME');
    expect(lookup.activeSortDir.value).toBe('asc');
  });

  it('list_query_error_sets_message', async () => {
    mockApiGet.mockResolvedValueOnce({ success: false, error: { message: '查詢失敗' } });
    const lookup = useEquipmentLookup();

    await lookup.submitQuery({ locations: [], families: [], resource_names: [] });

    expect(lookup.listError.value).toBe('查詢失敗');
  });

  it('exportCsv_fetches_full_set_with_page_size_10000_and_current_filters_sort', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();
    await lookup.submitQuery({ locations: ['LOC-A'], families: [], resource_names: [] });

    mockApiGet.mockResolvedValueOnce(mockListResponse());
    await lookup.exportCsv();

    const exportCallIndex = mockApiGet.mock.calls.length - 1;
    const params = (mockApiGet.mock.calls[exportCallIndex][1] as { params: Record<string, unknown> }).params;
    expect(params.page_size).toBe(10000);
    expect(params.locations).toEqual(['LOC-A']);
    expect(params.sort_by).toBe('RESOURCENAME');
    expect(lookup.isExporting.value).toBe(false);
    expect(lookup.listError.value).toBe('');
  });

  it('exportCsv_error_sets_message', async () => {
    mockApiGet.mockResolvedValueOnce(mockListResponse());
    const lookup = useEquipmentLookup();
    await lookup.submitQuery({ locations: [], families: [], resource_names: [] });

    mockApiGet.mockResolvedValueOnce({ success: false, error: { message: '匯出失敗' } });
    await lookup.exportCsv();

    expect(lookup.listError.value).toBe('匯出失敗');
  });
});

describe('buildEquipmentCsv', () => {
  it('emits_header_only_for_empty_rows', () => {
    expect(buildEquipmentCsv([])).toBe('編號,機台位置,機型,供應商,廠商型號,工站');
  });

  it('builds_rows_in_column_order_with_null_as_empty_string', () => {
    const csv = buildEquipmentCsv([
      {
        RESOURCENAME: 'R001',
        LOCATIONNAME: 'LOC-A',
        RESOURCEFAMILYNAME: 'FAM-A',
        VENDORNAME: null,
        VENDORMODEL: 'ModelX',
        WORKCENTERNAME: 'WC1',
      },
    ]);
    const lines = csv.split('\n');
    expect(lines[0]).toBe('編號,機台位置,機型,供應商,廠商型號,工站');
    expect(lines[1]).toBe('R001,LOC-A,FAM-A,,ModelX,WC1');
  });

  it('escapes_values_containing_commas', () => {
    const csv = buildEquipmentCsv([
      {
        RESOURCENAME: 'R001',
        LOCATIONNAME: 'LOC-A, Bldg 2',
        RESOURCEFAMILYNAME: 'FAM-A',
        VENDORNAME: 'V1',
        VENDORMODEL: 'M1',
        WORKCENTERNAME: 'WC1',
      },
    ]);
    expect(csv.split('\n')[1]).toContain('"LOC-A, Bldg 2"');
  });
});
