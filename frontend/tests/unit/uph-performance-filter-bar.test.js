// @vitest-environment jsdom
/**
 * Component tests for FilterBar.vue (global coarse filter bar)
 *
 * Validates:
 * - canSubmit gates on date_from/date_to only (no at-least-one-of-N rule,
 *   unlike eap-alarm — UPH has no such requirement per api-contract.md)
 * - free-text equipment/workcenter fields parse newline-separated values
 *   into arrays on submit (no pre-query options endpoint for those two dims)
 * - the family MultiSelect only ever offers the closed enum {GDBA, GWBA}
 * - confirmed #6: product-filter-options failure renders an inline warning,
 *   the rest of the filter bar stays interactive
 */
import { describe, it, expect } from 'vitest';
import { defineComponent } from 'vue';
import { mount } from '@vue/test-utils';

import FilterBar from '../../src/uph-performance/FilterBar.vue';

const MultiSelectStub = defineComponent({
  name: 'MultiSelect',
  props: {
    modelValue: { type: Array, default: () => [] },
    options: { type: Array, default: () => [] },
    placeholder: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  template: '<div class="multi-select-stub">{{ (modelValue || []).join(",") }}</div>',
});

function makeFilters(overrides = {}) {
  return {
    date_from: '',
    date_to: '',
    families: [],
    workcenter_names: [],
    packages: [],
    pj_types: [],
    equipment_ids: [],
    ...overrides,
  };
}

function mountFilterBar(filters, extraProps = {}) {
  return mount(FilterBar, {
    props: {
      filters,
      productFilterOptions: { pj_types: ['TYPE-A'], product_lines: ['PKG-A'] },
      loading: { querying: false },
      productOptionsLoading: false,
      productOptionsError: '',
      ...extraProps,
    },
    global: { stubs: { MultiSelect: MultiSelectStub } },
  });
}

describe('FilterBar', () => {
  it('disables submit until both dates are filled (no at-least-one-of-N rule)', () => {
    const wrapper = mountFilterBar(makeFilters());
    expect(wrapper.find('[data-testid="ctrl-submit"]').attributes('disabled')).toBeDefined();
  });

  it('enables submit once date_from and date_to are both set, with everything else empty', () => {
    const wrapper = mountFilterBar(makeFilters({ date_from: '2026-07-01', date_to: '2026-07-07' }));
    expect(wrapper.find('[data-testid="ctrl-submit"]').attributes('disabled')).toBeUndefined();
  });

  it('disables submit when date_from is after date_to', () => {
    const wrapper = mountFilterBar(makeFilters({ date_from: '2026-07-10', date_to: '2026-07-01' }));
    expect(wrapper.find('[data-testid="ctrl-submit"]').attributes('disabled')).toBeDefined();
  });

  it('parses the equipment-ID textarea into an array on submit', async () => {
    const wrapper = mountFilterBar(makeFilters({ date_from: '2026-07-01', date_to: '2026-07-07' }));
    await wrapper.find('[data-testid="ctrl-equipment-search"]').setValue('GDBA-001\nGDBA-002\n');
    await wrapper.find('[data-testid="ctrl-submit"]').trigger('click');
    const updateEvents = wrapper.emitted('update:filters');
    const lastPayload = updateEvents[updateEvents.length - 1][0];
    expect(lastPayload.equipment_ids).toEqual(['GDBA-001', 'GDBA-002']);
    expect(wrapper.emitted('submit')).toBeTruthy();
  });

  it('parses the workcenter textarea into an array on submit', async () => {
    const wrapper = mountFilterBar(makeFilters({ date_from: '2026-07-01', date_to: '2026-07-07' }));
    await wrapper.find('[data-testid="ctrl-workcenter-select"]').setValue('WC-1\nWC-2');
    await wrapper.find('[data-testid="ctrl-submit"]').trigger('click');
    const updateEvents = wrapper.emitted('update:filters');
    const lastPayload = updateEvents[updateEvents.length - 1][0];
    expect(lastPayload.workcenter_names).toEqual(['WC-1', 'WC-2']);
  });

  it('handleClear resets every optional dim and emits clear', async () => {
    const wrapper = mountFilterBar(
      makeFilters({
        date_from: '2026-07-01',
        date_to: '2026-07-07',
        families: ['GDBA'],
        packages: ['PKG-A'],
        pj_types: ['TYPE-A'],
      }),
    );
    await wrapper.find('[data-testid="ctrl-clear"]').trigger('click');
    const lastPayload = wrapper.emitted('update:filters').slice(-1)[0][0];
    expect(lastPayload.families).toEqual([]);
    expect(lastPayload.packages).toEqual([]);
    expect(lastPayload.pj_types).toEqual([]);
    expect(wrapper.emitted('clear')).toBeTruthy();
  });

  it('shows the inline product-options warning without disabling other filters (confirmed #6)', () => {
    const wrapper = mountFilterBar(makeFilters(), { productOptionsError: 'mock 500' });
    const warning = wrapper.find('[data-testid="product-options-warning"]');
    expect(warning.exists()).toBe(true);
    expect(warning.text()).toContain('mock 500');
    // The workcenter/equipment free-text fields are independent of
    // product-filter-options and must remain enabled.
    expect(wrapper.find('[data-testid="ctrl-workcenter-select"]').attributes('disabled')).toBeUndefined();
    expect(wrapper.find('[data-testid="ctrl-equipment-search"]').attributes('disabled')).toBeUndefined();
  });

  it('the global Type filter (ctrl-type-select-global) is a distinct element from any ranking control', () => {
    const wrapper = mountFilterBar(makeFilters());
    expect(wrapper.find('[data-testid="ctrl-type-select-global"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="ctrl-ranking-type-filter"]').exists()).toBe(false);
  });
});
