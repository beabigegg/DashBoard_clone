/**
 * Unit tests for useEapAlarmFilter composable
 *
 * Validates:
 * - _lastCommitted re-sync after fetchFilterOptions (snapshot-diff rule)
 * - buildFineFilterParams returns correct URL params
 * - buildCoarseParams forwards all 5 dims correctly
 * - parseLotIdText normalizes textarea input
 * - Fine filter state management
 * - Default date range is set correctly
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock onMounted so the composable can be called outside a component context
// without Vue warnings. The product-filter-options fetch is not under test here.
vi.mock('vue', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    onMounted: vi.fn((fn) => {
      // no-op in unit test: do not invoke fn
    }),
  };
});

// Mock apiGet so no real HTTP call is made
vi.mock('../../src/core/api.js', () => ({
  apiGet: vi.fn().mockResolvedValue({ data: { pj_types: [], product_lines: [], pj_bops: [] } }),
  apiPost: vi.fn().mockResolvedValue({}),
}));

import { useEapAlarmFilter } from '../../src/eap-alarm/composables/useEapAlarmFilter.js';

// Vitest runs in jsdom environment; Vue reactivity should work fine.

describe('useEapAlarmFilter', () => {
  let filter;

  beforeEach(() => {
    filter = useEapAlarmFilter();
  });

  it('initializes coarse filter with empty machines list', () => {
    expect(Array.isArray(filter.coarseFilter.machines)).toBe(true);
    expect(filter.coarseFilter.machines).toHaveLength(0);
  });

  it('initializes fine filter as empty', () => {
    expect(filter.fineFilter.alarm_text).toHaveLength(0);
    expect(filter.fineFilter.eqp_id).toHaveLength(0);
  });

  it('setDefaultDateRange sets date_from before date_to', () => {
    filter.setDefaultDateRange();
    expect(filter.coarseFilter.date_from).toBeTruthy();
    expect(filter.coarseFilter.date_to).toBeTruthy();
    expect(filter.coarseFilter.date_from < filter.coarseFilter.date_to).toBe(true);
  });

  describe('_lastCommitted re-sync (snapshot-diff rule)', () => {
    it('applyFilterOptions re-syncs _lastCommitted from current fine filter selection', () => {
      // Set fine filter before calling applyFilterOptions
      filter.fineFilter.alarm_text = ['ALARM_A', 'ALARM_B'];
      filter.fineFilter.eqp_id = ['EQ-01'];

      const mockOptions = {
        alarm_text_options: ['ALARM_A', 'ALARM_B', 'ALARM_C'],
        equipment_id_options: ['EQ-01', 'EQ-02'],
      };

      filter.applyFilterOptions(mockOptions);

      // Filter options should be applied
      expect(filter.filterOptions.alarm_text_options).toEqual(['ALARM_A', 'ALARM_B', 'ALARM_C']);
      expect(filter.filterOptions.equipment_id_options).toEqual(['EQ-01', 'EQ-02']);

      // hasFineFilterChanged() should return false right after applyFilterOptions
      // because _lastCommitted was re-synced from current selection
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('hasFineFilterChanged returns false immediately after applyFilterOptions', () => {
      filter.fineFilter.alarm_text = ['TEST'];
      filter.applyFilterOptions({
        alarm_text_options: ['TEST', 'OTHER'],
        equipment_id_options: [],
      });
      // _lastCommitted re-synced: no change
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('hasFineFilterChanged returns true when fine filter changes after re-sync', () => {
      filter.applyFilterOptions({
        alarm_text_options: ['ALARM_A'],
        equipment_id_options: [],
      });
      // _lastCommitted = {alarm_text: [], eqp_id: []}

      // Now change the fine filter
      filter.fineFilter.alarm_text = ['ALARM_A'];

      expect(filter.hasFineFilterChanged()).toBe(true);
    });

    it('resetFineFilter re-syncs _lastCommitted', () => {
      filter.fineFilter.alarm_text = ['ALARM_A'];

      filter.resetFineFilter();

      // After reset, fine filter is empty and _lastCommitted is re-synced
      expect(filter.fineFilter.alarm_text).toHaveLength(0);
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('commitFineFilter re-syncs _lastCommitted from current selection', () => {
      filter.fineFilter.alarm_text = ['ALARM_A'];
      // Before commit: changed
      expect(filter.hasFineFilterChanged()).toBe(true);

      filter.commitFineFilter();
      // After commit: no longer changed
      expect(filter.hasFineFilterChanged()).toBe(false);
    });
  });

  describe('buildFineFilterParams', () => {
    it('returns only query_id when fine filter is empty', () => {
      filter.setQueryId('q-001');
      const params = filter.buildFineFilterParams();
      expect(params.query_id).toBe('q-001');
      expect(params['alarm_text[]']).toBeUndefined();
      expect(params['equipment_id[]']).toBeUndefined();
    });

    it('includes alarm_text array when filter is set', () => {
      filter.setQueryId('q-002');
      filter.fineFilter.alarm_text = ['ALARM_A', 'ALARM_B'];
      const params = filter.buildFineFilterParams();
      expect(params['alarm_text[]']).toEqual(['ALARM_A', 'ALARM_B']);
    });

    it('includes eqp_id array as equipment_id when filter is set', () => {
      filter.setQueryId('q-004');
      filter.fineFilter.eqp_id = ['EQ-01', 'EQ-02'];
      const params = filter.buildFineFilterParams();
      expect(params['equipment_id[]']).toEqual(['EQ-01', 'EQ-02']);
    });
  });

  describe('setQueryId / spoolReady', () => {
    it('sets queryId and spoolReady on non-empty id', () => {
      filter.setQueryId('q-xyz');
      expect(filter.queryId.value).toBe('q-xyz');
      expect(filter.spoolReady.value).toBe(true);
    });

    it('sets spoolReady to false on empty id', () => {
      filter.setQueryId('');
      expect(filter.spoolReady.value).toBe(false);
    });
  });

  describe('buildCoarseParams', () => {
    beforeEach(() => {
      filter.setDefaultDateRange();
    });

    it('forwards lot_ids as separate param', () => {
      filter.coarseFilter.lot_ids = ['LOT001', 'LOT002'];
      const params = filter.buildCoarseParams();
      expect(params.lot_ids).toEqual(['LOT001', 'LOT002']);
    });

    it('forwards pj_types as separate param', () => {
      filter.coarseFilter.machines = ['MACHINE-1']; // satisfy at-least-one (not in composable)
      filter.coarseFilter.pj_types = ['TYPE-A', 'TYPE-B'];
      const params = filter.buildCoarseParams();
      expect(params.pj_types).toEqual(['TYPE-A', 'TYPE-B']);
    });

    it('forwards product_lines as separate param', () => {
      filter.coarseFilter.product_lines = ['PKG-X'];
      const params = filter.buildCoarseParams();
      expect(params.product_lines).toEqual(['PKG-X']);
    });

    it('forwards pj_bops as separate param', () => {
      filter.coarseFilter.pj_bops = ['BOP-1'];
      const params = filter.buildCoarseParams();
      expect(params.pj_bops).toEqual(['BOP-1']);
    });

    it('omits empty dims from params', () => {
      // All new dims are empty; only date fields should appear
      filter.coarseFilter.lot_ids = [];
      filter.coarseFilter.pj_types = [];
      filter.coarseFilter.product_lines = [];
      filter.coarseFilter.pj_bops = [];
      filter.coarseFilter.machines = [];
      const params = filter.buildCoarseParams();
      expect(params).not.toHaveProperty('lot_ids');
      expect(params).not.toHaveProperty('pj_types');
      expect(params).not.toHaveProperty('product_lines');
      expect(params).not.toHaveProperty('pj_bops');
      expect(params).not.toHaveProperty('machines');
    });

    it('omits machines when machines array is empty', () => {
      filter.coarseFilter.machines = [];
      filter.coarseFilter.lot_ids = ['LOT001'];
      const params = filter.buildCoarseParams();
      expect(params).not.toHaveProperty('machines');
      // lot_ids should still be present
      expect(params.lot_ids).toEqual(['LOT001']);
    });

    it('includes machines in params when non-empty', () => {
      filter.coarseFilter.machines = ['MCH-1'];
      const params = filter.buildCoarseParams();
      expect(params.machines).toEqual(['MCH-1']);
    });

    it('always includes date_from and date_to', () => {
      const params = filter.buildCoarseParams();
      expect(params.date_from).toBeTruthy();
      expect(params.date_to).toBeTruthy();
    });
  });

  describe('parseLotIdText', () => {
    it('splits textarea input by newline and trims each line', () => {
      const result = filter.parseLotIdText('LOT001\nLOT002\n');
      expect(result).toEqual(['LOT001', 'LOT002']);
    });

    it('trims whitespace from each line', () => {
      const result = filter.parseLotIdText('  LOT001  \n  LOT002  \n');
      expect(result).toEqual(['LOT001', 'LOT002']);
    });

    it('filters out blank lines', () => {
      const result = filter.parseLotIdText('LOT001\n\nLOT002\n\n');
      expect(result).toEqual(['LOT001', 'LOT002']);
    });

    it('returns empty array for empty string', () => {
      const result = filter.parseLotIdText('');
      expect(result).toEqual([]);
    });

    it('returns empty array for whitespace-only input', () => {
      const result = filter.parseLotIdText('   \n   \n');
      expect(result).toEqual([]);
    });

    it('parses single LOT ID without trailing newline', () => {
      const result = filter.parseLotIdText('LOT001');
      expect(result).toEqual(['LOT001']);
    });
  });

  describe('coarseFilter new fields initialization', () => {
    it('initializes lot_ids as empty array', () => {
      expect(Array.isArray(filter.coarseFilter.lot_ids)).toBe(true);
      expect(filter.coarseFilter.lot_ids).toHaveLength(0);
    });

    it('initializes pj_types as empty array', () => {
      expect(Array.isArray(filter.coarseFilter.pj_types)).toBe(true);
      expect(filter.coarseFilter.pj_types).toHaveLength(0);
    });

    it('initializes product_lines as empty array', () => {
      expect(Array.isArray(filter.coarseFilter.product_lines)).toBe(true);
      expect(filter.coarseFilter.product_lines).toHaveLength(0);
    });

    it('initializes pj_bops as empty array', () => {
      expect(Array.isArray(filter.coarseFilter.pj_bops)).toBe(true);
      expect(filter.coarseFilter.pj_bops).toHaveLength(0);
    });
  });

  describe('productFilterOptions', () => {
    it('initializes with empty option arrays', () => {
      expect(filter.productFilterOptions.value.pj_types).toEqual([]);
      expect(filter.productFilterOptions.value.product_lines).toEqual([]);
      expect(filter.productFilterOptions.value.pj_bops).toEqual([]);
      expect(filter.productFilterOptions.value.updated_at).toBeNull();
    });
  });

  describe('productOptionsLoading', () => {
    it('is exposed as a ref and initializes to false', () => {
      expect(filter.productOptionsLoading).toBeDefined();
      expect(filter.productOptionsLoading.value).toBe(false);
    });
  });
});
