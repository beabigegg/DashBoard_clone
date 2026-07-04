// @vitest-environment jsdom
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
 * - FilterBar.vue handleSubmit family-without-machine expansion (AC-10/D-8/IP-12)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { defineComponent } from 'vue';
import { shallowMount } from '@vue/test-utils';

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
import FilterBar from '../../src/eap-alarm/FilterBar.vue';

// Vitest runs in jsdom environment; Vue reactivity should work fine.

// ── MultiSelect stub (mirrors the pattern used in App.cross-filter tests) ────
const MultiSelectStub = defineComponent({
  name: 'MultiSelect',
  props: {
    modelValue: { type: Array, default: () => [] },
    options: { type: Array, default: () => [] },
    placeholder: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    searchable: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  template: '<div class="multi-select-stub">{{ (modelValue || []).join(",") }}</div>',
});

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
    expect(filter.fineFilter.lot_id).toHaveLength(0);
    expect(filter.fineFilter.pj_type).toHaveLength(0);
    expect(filter.fineFilter.product_line).toHaveLength(0);
    expect(filter.fineFilter.pj_bop).toHaveLength(0);
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

    it('includes product-dim arrays when filters are set', () => {
      filter.setQueryId('q-005');
      filter.fineFilter.lot_id = ['LOT-001'];
      filter.fineFilter.pj_type = ['TypeA'];
      filter.fineFilter.product_line = ['LineB'];
      filter.fineFilter.pj_bop = ['BopC'];
      const params = filter.buildFineFilterParams();
      expect(params['lot_id[]']).toEqual(['LOT-001']);
      expect(params['pj_type[]']).toEqual(['TypeA']);
      expect(params['product_line[]']).toEqual(['LineB']);
      expect(params['pj_bop[]']).toEqual(['BopC']);
    });

    it('omits product-dim params when their filters are empty', () => {
      filter.setQueryId('q-006');
      const params = filter.buildFineFilterParams();
      expect(params['lot_id[]']).toBeUndefined();
      expect(params['pj_type[]']).toBeUndefined();
      expect(params['product_line[]']).toBeUndefined();
      expect(params['pj_bop[]']).toBeUndefined();
    });
  });

  describe('product-dim fine filter state', () => {
    it('applyFilterOptions applies new option lists and re-syncs snapshot', () => {
      filter.fineFilter.pj_type = ['TypeA'];
      filter.applyFilterOptions({
        alarm_text_options: [],
        equipment_id_options: [],
        lot_id_options: ['LOT-001'],
        pj_type_options: ['TypeA', 'TypeB'],
        product_line_options: ['LineA'],
        pj_bop_options: ['BopA'],
      });
      expect(filter.filterOptions.lot_id_options).toEqual(['LOT-001']);
      expect(filter.filterOptions.pj_type_options).toEqual(['TypeA', 'TypeB']);
      expect(filter.filterOptions.product_line_options).toEqual(['LineA']);
      expect(filter.filterOptions.pj_bop_options).toEqual(['BopA']);
      expect(filter.hasFineFilterChanged()).toBe(false);
    });

    it('hasFineFilterChanged detects change on a product-dim axis', () => {
      filter.commitFineFilter();
      filter.fineFilter.product_line = ['LineA'];
      expect(filter.hasFineFilterChanged()).toBe(true);
    });

    it('resetFineFilter clears product-dim axes', () => {
      filter.fineFilter.lot_id = ['LOT-001'];
      filter.fineFilter.pj_bop = ['BopA'];
      filter.resetFineFilter();
      expect(filter.fineFilter.lot_id).toHaveLength(0);
      expect(filter.fineFilter.pj_bop).toHaveLength(0);
      expect(filter.hasFineFilterChanged()).toBe(false);
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

// ── AC-10 / D-8 / IP-12: FilterBar family-without-machine expansion ──────────
describe('FilterBar handleSubmit family expansion', () => {
  const RESOURCE_OPTIONS = {
    families: ['GWBK', 'GDBA'],
    resources: [
      { id: 'GWBK-0001', name: 'GWBK-0001', family: 'GWBK', workcenterGroup: 'WB' },
      { id: 'GWBK-0002', name: 'GWBK-0002', family: 'GWBK', workcenterGroup: 'WB' },
      { id: 'GWBK-0241', name: 'GWBK-0241', family: 'GWBK', workcenterGroup: 'WB' },
      { id: 'GDBA-001', name: 'GDBA-001', family: 'GDBA', workcenterGroup: 'DB' },
    ],
  };

  const PRODUCT_FILTER_OPTIONS = {
    pj_types: [],
    product_lines: [],
    pj_bops: [],
    updated_at: null,
  };

  function makeFilters(overrides = {}) {
    return {
      date_from: '2026-06-01',
      date_to: '2026-06-30',
      machines: [],
      lot_ids: [],
      pj_types: [],
      product_lines: [],
      pj_bops: [],
      ...overrides,
    };
  }

  function mountFilterBar(filters) {
    return shallowMount(FilterBar, {
      props: {
        filters,
        resourceOptions: RESOURCE_OPTIONS,
        productFilterOptions: PRODUCT_FILTER_OPTIONS,
        loading: { querying: false },
        productOptionsLoading: false,
      },
      global: {
        stubs: {
          MultiSelect: MultiSelectStub,
        },
      },
    });
  }

  it('family selected + machines=[] expands submitted machines to every name in the family machineOptions', async () => {
    // family-only selection (no lot_ids/machines/product dims) now satisfies
    // canSubmit on its own — no workaround axis needed.
    const filters = makeFilters({ machines: [] });
    const wrapper = mountFilterBar(filters);

    // Select the GWBK family via the 型號 MultiSelect stub (first MultiSelect
    // rendered in the template is the family cascade selector).
    const multiSelects = wrapper.findAllComponents(MultiSelectStub);
    const familySelect = multiSelects[0];
    await familySelect.vm.$emit('update:modelValue', ['GWBK']);

    await wrapper.find('[data-testid="coarse-submit-btn"]').trigger('click');

    const updateEvents = wrapper.emitted('update:filters');
    expect(updateEvents).toBeTruthy();
    const lastPayload = updateEvents[updateEvents.length - 1][0];

    expect(lastPayload.machines).toEqual(
      expect.arrayContaining(['GWBK-0001', 'GWBK-0002', 'GWBK-0241'])
    );
    expect(lastPayload.machines).toHaveLength(3);
    expect(lastPayload.machines).not.toContain('GDBA-001');

    expect(wrapper.emitted('submit')).toBeTruthy();
  });

  it('canSubmit becomes true when only a family is selected (no machines, lot_ids, or product dims)', async () => {
    const filters = makeFilters(); // machines/lot_ids/pj_types/product_lines/pj_bops all empty
    const wrapper = mountFilterBar(filters);

    const submitBtn = wrapper.find('[data-testid="coarse-submit-btn"]');
    // Before any family selection: at-least-one-of-three is not satisfied.
    expect(submitBtn.attributes('disabled')).toBeDefined();

    const multiSelects = wrapper.findAllComponents(MultiSelectStub);
    const familySelect = multiSelects[0];
    await familySelect.vm.$emit('update:modelValue', ['GWBK']);

    // Family-only selection now satisfies canSubmit on its own.
    expect(wrapper.find('[data-testid="coarse-submit-btn"]').attributes('disabled')).toBeUndefined();
  });

  it('family selected + specific machines already chosen submits exactly those machines unchanged', async () => {
    const filters = makeFilters({ machines: ['GWBK-0241'] });
    const wrapper = mountFilterBar(filters); // machines non-empty already satisfies canSubmit

    const multiSelects = wrapper.findAllComponents(MultiSelectStub);
    const familySelect = multiSelects[0];
    await familySelect.vm.$emit('update:modelValue', ['GWBK']);

    await wrapper.find('[data-testid="coarse-submit-btn"]').trigger('click');

    const updateEvents = wrapper.emitted('update:filters');
    expect(updateEvents).toBeTruthy();
    const lastPayload = updateEvents[updateEvents.length - 1][0];

    expect(lastPayload.machines).toEqual(['GWBK-0241']);
  });

  it('no family and no machine selected leaves submitted machines as empty array unchanged', async () => {
    // canSubmit requires at-least-one-of-three; set lot_ids (orthogonal to
    // family/machine) so the submit button is enabled without touching the
    // 型號/機台 axes under test here.
    const filters = makeFilters({ machines: [], lot_ids: ['LOT-001'] });
    const wrapper = mountFilterBar(filters);

    // No family selection performed — cascade.families stays empty.
    await wrapper.find('[data-testid="coarse-submit-btn"]').trigger('click');

    const updateEvents = wrapper.emitted('update:filters');
    expect(updateEvents).toBeTruthy();
    const lastPayload = updateEvents[updateEvents.length - 1][0];

    expect(lastPayload.machines).toEqual([]);
  });
});
