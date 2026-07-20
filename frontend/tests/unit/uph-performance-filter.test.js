// @vitest-environment jsdom
/**
 * Unit tests for useUphPerformanceFilter composable
 *
 * Validates:
 * - _lastCommitted re-sync after fetchFilterOptions (snapshot-diff rule)
 * - buildFineFilterParams / buildCoarseParams / buildRankingParams shapes
 * - The ranking Type filter is a wholly separate ref, defaulting to empty,
 *   never sharing state with the global Type filter (coarseFilter.pj_types)
 *   (interaction-design.md §Confirmed #2/#7 — highest-risk consistency point)
 * - parseMultiLineText normalizes free-text textarea input
 * - fine filter axes: equipment_id/package/pj_type/die_count/wire_count
 *   (workcenter_name removed — tier-1's 工作站 cascade is now the page's
 *   only 工作站 control)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('vue', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    onMounted: vi.fn(() => {
      // no-op in unit test: do not invoke the product-filter-options fetch
    }),
  };
});

vi.mock('../../src/core/api.js', () => ({
  apiGet: vi.fn().mockResolvedValue({ data: { pj_types: [], product_lines: [] } }),
  apiPost: vi.fn().mockResolvedValue({}),
}));

import { useUphPerformanceFilter } from '../../src/uph-performance/composables/useUphPerformanceFilter.js';

describe('useUphPerformanceFilter', () => {
  let filter;

  beforeEach(() => {
    filter = useUphPerformanceFilter();
  });

  it('initializes coarse filter with empty arrays for every optional dim', () => {
    expect(filter.coarseFilter.families).toEqual([]);
    expect(filter.coarseFilter.workcenter_names).toEqual([]);
    expect(filter.coarseFilter.packages).toEqual([]);
    expect(filter.coarseFilter.pj_types).toEqual([]);
    expect(filter.coarseFilter.equipment_ids).toEqual([]);
  });

  it('initializes fine filter as empty', () => {
    expect(filter.fineFilter.equipment_id).toHaveLength(0);
    expect(filter.fineFilter.package).toHaveLength(0);
    expect(filter.fineFilter.pj_type).toHaveLength(0);
    expect(filter.fineFilter.die_count).toHaveLength(0);
    expect(filter.fineFilter.wire_count).toHaveLength(0);
    expect(filter.fineFilter.workcenter_name).toBeUndefined();
  });

  it('setDefaultDateRange sets date_from before date_to', () => {
    filter.setDefaultDateRange();
    expect(filter.coarseFilter.date_from).toBeTruthy();
    expect(filter.coarseFilter.date_to).toBeTruthy();
    expect(filter.coarseFilter.date_from < filter.coarseFilter.date_to).toBe(true);
  });

  describe('ranking Type filter independence (§Confirmed #2/#7)', () => {
    it('defaults to an empty array (none selected)', () => {
      expect(filter.rankingTypeFilter.value).toEqual([]);
    });

    it('is a wholly separate ref from coarseFilter.pj_types', () => {
      filter.coarseFilter.pj_types = ['TYPE-A', 'TYPE-B'];
      // Setting the global Type filter must never populate the ranking filter.
      expect(filter.rankingTypeFilter.value).toEqual([]);
    });

    it('setting the ranking filter never mutates the global Type filter', () => {
      filter.coarseFilter.pj_types = ['TYPE-A'];
      filter.rankingTypeFilter.value = ['TYPE-B'];
      expect(filter.coarseFilter.pj_types).toEqual(['TYPE-A']);
      expect(filter.rankingTypeFilter.value).toEqual(['TYPE-B']);
    });

    it('resetRankingTypeFilter clears only the ranking filter', () => {
      filter.coarseFilter.pj_types = ['TYPE-A'];
      filter.rankingTypeFilter.value = ['TYPE-B'];
      filter.resetRankingTypeFilter();
      expect(filter.rankingTypeFilter.value).toEqual([]);
      expect(filter.coarseFilter.pj_types).toEqual(['TYPE-A']);
    });

    it('buildRankingParams returns null when nothing is selected', () => {
      expect(filter.buildRankingParams()).toBeNull();
    });

    it('buildRankingParams returns the pj_type[] param when a Type is selected', () => {
      filter.setQueryId('q-100');
      filter.rankingTypeFilter.value = ['TYPE-A', 'TYPE-B'];
      const params = filter.buildRankingParams();
      expect(params).toEqual({ query_id: 'q-100', 'pj_type[]': ['TYPE-A', 'TYPE-B'] });
    });
  });

  describe('_lastCommitted re-sync (snapshot-diff rule)', () => {
    it('applyFilterOptions re-syncs _lastCommitted from current fine filter selection', () => {
      filter.fineFilter.equipment_id = ['GDBA-001'];
      filter.applyFilterOptions({
        equipment_id_options: ['GDBA-001', 'GDBA-002'],
        package_options: [],
        pj_type_options: [],
        die_count_options: [],
        wire_count_options: [],
      });
      expect(filter.filterOptions.equipment_id_options).toEqual(['GDBA-001', 'GDBA-002']);
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('hasFineFilterChanged returns true when fine filter changes after re-sync', () => {
      filter.applyFilterOptions({
        equipment_id_options: ['GDBA-001'],
        package_options: [],
        pj_type_options: [],
        die_count_options: [],
        wire_count_options: [],
      });
      filter.fineFilter.equipment_id = ['GDBA-001'];
      expect(filter.hasFineFilterChanged()).toBe(true);
    });

    it('resetFineFilter re-syncs _lastCommitted', () => {
      filter.fineFilter.pj_type = ['TYPE-A'];
      filter.resetFineFilter();
      expect(filter.fineFilter.pj_type).toHaveLength(0);
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('commitFineFilter re-syncs _lastCommitted from current selection', () => {
      filter.fineFilter.package = ['PKG-1'];
      expect(filter.hasFineFilterChanged()).toBe(true);
      filter.commitFineFilter();
      expect(filter.hasFineFilterChanged()).toBe(false);
    });
  });

  describe('buildFineFilterParams', () => {
    it('returns only query_id when fine filter is empty', () => {
      filter.setQueryId('q-001');
      const params = filter.buildFineFilterParams();
      expect(params.query_id).toBe('q-001');
      expect(params['equipment_id[]']).toBeUndefined();
      expect(params['package[]']).toBeUndefined();
      expect(params['pj_type[]']).toBeUndefined();
      expect(params['die_count[]']).toBeUndefined();
      expect(params['wire_count[]']).toBeUndefined();
    });

    it('includes each fine-filter axis as an array param when set', () => {
      filter.setQueryId('q-002');
      filter.fineFilter.equipment_id = ['GDBA-001'];
      filter.fineFilter.package = ['PKG-A'];
      filter.fineFilter.pj_type = ['TYPE-A'];
      filter.fineFilter.die_count = ['2'];
      filter.fineFilter.wire_count = ['4'];
      const params = filter.buildFineFilterParams();
      expect(params['equipment_id[]']).toEqual(['GDBA-001']);
      expect(params['package[]']).toEqual(['PKG-A']);
      expect(params['pj_type[]']).toEqual(['TYPE-A']);
      expect(params['die_count[]']).toEqual(['2']);
      expect(params['wire_count[]']).toEqual(['4']);
    });
  });

  describe('buildCoarseParams', () => {
    beforeEach(() => {
      filter.setDefaultDateRange();
    });

    it('always includes date_from and date_to', () => {
      const params = filter.buildCoarseParams();
      expect(params.date_from).toBeTruthy();
      expect(params.date_to).toBeTruthy();
    });

    it('omits every optional dim when empty', () => {
      const params = filter.buildCoarseParams();
      expect(params).not.toHaveProperty('families');
      expect(params).not.toHaveProperty('workcenter_names');
      expect(params).not.toHaveProperty('packages');
      expect(params).not.toHaveProperty('pj_types');
      expect(params).not.toHaveProperty('equipment_ids');
    });

    it('forwards families as a closed-enum subset', () => {
      filter.coarseFilter.families = ['GDBA'];
      const params = filter.buildCoarseParams();
      expect(params.families).toEqual(['GDBA']);
    });

    it('forwards workcenter_names, packages, pj_types, equipment_ids when set', () => {
      filter.coarseFilter.workcenter_names = ['WC-1'];
      filter.coarseFilter.packages = ['PKG-A'];
      filter.coarseFilter.pj_types = ['TYPE-A'];
      filter.coarseFilter.equipment_ids = ['GDBA-001', 'GDBA-002'];
      const params = filter.buildCoarseParams();
      expect(params.workcenter_names).toEqual(['WC-1']);
      expect(params.packages).toEqual(['PKG-A']);
      expect(params.pj_types).toEqual(['TYPE-A']);
      expect(params.equipment_ids).toEqual(['GDBA-001', 'GDBA-002']);
    });
  });

  describe('parseMultiLineText', () => {
    it('splits by newline, trims, and drops blank lines', () => {
      expect(filter.parseMultiLineText('WC-1\n  WC-2  \n\nWC-3\n')).toEqual(['WC-1', 'WC-2', 'WC-3']);
    });

    it('returns an empty array for blank input', () => {
      expect(filter.parseMultiLineText('   \n  ')).toEqual([]);
    });
  });

  describe('setQueryId / spoolReady', () => {
    it('sets queryId and spoolReady on a non-empty id', () => {
      filter.setQueryId('q-xyz');
      expect(filter.queryId.value).toBe('q-xyz');
      expect(filter.spoolReady.value).toBe(true);
    });

    it('sets spoolReady to false on an empty id', () => {
      filter.setQueryId('');
      expect(filter.spoolReady.value).toBe(false);
    });
  });

  describe('product-filter-options composable state removed', () => {
    it('no longer exposes productFilterOptions/productOptionsLoading/productOptionsError/loadProductFilterOptions (Package/Type moved to fine filter)', () => {
      expect(filter.productFilterOptions).toBeUndefined();
      expect(filter.productOptionsLoading).toBeUndefined();
      expect(filter.productOptionsError).toBeUndefined();
      expect(filter.loadProductFilterOptions).toBeUndefined();
    });
  });

  describe('die_count / wire_count fine filter (晶粒數 / 打線數)', () => {
    it('buildFineFilterParams forwards die_count[] and wire_count[] independently', () => {
      filter.setQueryId('q-003');
      filter.fineFilter.die_count = ['2', '4'];
      const params = filter.buildFineFilterParams();
      expect(params['die_count[]']).toEqual(['2', '4']);
      expect(params['wire_count[]']).toBeUndefined();
    });

    it('applyFilterOptions populates die_count_options / wire_count_options', () => {
      filter.applyFilterOptions({
        equipment_id_options: [],
        package_options: [],
        pj_type_options: [],
        die_count_options: ['1', '2', '4'],
        wire_count_options: ['4', '8'],
      });
      expect(filter.filterOptions.die_count_options).toEqual(['1', '2', '4']);
      expect(filter.filterOptions.wire_count_options).toEqual(['4', '8']);
    });

    it('resetFineFilter clears die_count/wire_count and re-syncs _lastCommitted', () => {
      filter.fineFilter.die_count = ['2'];
      filter.fineFilter.wire_count = ['4'];
      filter.resetFineFilter();
      expect(filter.fineFilter.die_count).toHaveLength(0);
      expect(filter.fineFilter.wire_count).toHaveLength(0);
      expect(filter.hasFineFilterChanged()).toBe(false);
    });
  });
});
