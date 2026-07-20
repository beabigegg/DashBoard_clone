// @vitest-environment jsdom
/**
 * Component tests for FineFilterBar.vue (tier-2 fine filter).
 *
 * Validates:
 * - Each fine-filter axis (equipment_id/package/pj_type/die_count/wire_count)
 *   binds its own MultiSelect to fineFilter[key] / filterOptions[key + '_options']
 * - Changing a MultiSelect calls onFilterChange with the axis key + new values
 *   and emits 'change' (mirrors the existing Package/pj_type wiring)
 * - 工作站 (workcenter_name) is no longer rendered here — it stays a
 *   tier-1-only control (FilterBar.vue's ctrl-workcenter-select)
 */
import { describe, it, expect } from 'vitest';
import { defineComponent } from 'vue';
import { mount } from '@vue/test-utils';

import FineFilterBar from '../../src/uph-performance/FineFilterBar.vue';

const MultiSelectStub = defineComponent({
  name: 'MultiSelect',
  props: {
    modelValue: { type: Array, default: () => [] },
    options: { type: Array, default: () => [] },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'dropdown-close'],
  template: '<div class="multi-select-stub">{{ (modelValue || []).join(",") }}</div>',
});

function makeFineFilter(overrides = {}) {
  return {
    equipment_id: [],
    package: [],
    pj_type: [],
    die_count: [],
    wire_count: [],
    ...overrides,
  };
}

function makeFilterOptions(overrides = {}) {
  return {
    equipment_id_options: ['GDBA-001'],
    package_options: ['PKG-A'],
    pj_type_options: ['TYPE-A'],
    die_count_options: ['2', '4'],
    wire_count_options: ['4', '8'],
    ...overrides,
  };
}

function mountFineFilterBar(fineFilter, filterOptions) {
  return mount(FineFilterBar, {
    props: { fineFilter, filterOptions },
    global: { stubs: { MultiSelect: MultiSelectStub } },
  });
}

function findSelect(wrapper, testid) {
  return wrapper
    .findAllComponents(MultiSelectStub)
    .find((c) => c.attributes('data-testid') === testid);
}

describe('FineFilterBar', () => {
  it('no longer renders a 工作站 control (tier-1 is the sole 工作站 control)', () => {
    const wrapper = mountFineFilterBar(makeFineFilter(), makeFilterOptions());
    expect(wrapper.find('[data-testid="fine-workcenter-select"]').exists()).toBe(false);
  });

  it('renders 晶粒數 (die_count) bound to fineFilter.die_count / filterOptions.die_count_options', () => {
    const wrapper = mountFineFilterBar(makeFineFilter({ die_count: ['2'] }), makeFilterOptions());
    const select = findSelect(wrapper, 'fine-die-count-select');
    expect(select).toBeTruthy();
    expect(select.props('modelValue')).toEqual(['2']);
    expect(select.props('options')).toEqual(['2', '4']);
  });

  it('renders 打線數 (wire_count) bound to fineFilter.wire_count / filterOptions.wire_count_options', () => {
    const wrapper = mountFineFilterBar(makeFineFilter({ wire_count: ['4'] }), makeFilterOptions());
    const select = findSelect(wrapper, 'fine-wire-count-select');
    expect(select).toBeTruthy();
    expect(select.props('modelValue')).toEqual(['4']);
    expect(select.props('options')).toEqual(['4', '8']);
  });

  it('changing 晶粒數 emits change and mutates fineFilter.die_count (mirrors Package/Type wiring)', async () => {
    const fineFilter = makeFineFilter();
    const wrapper = mountFineFilterBar(fineFilter, makeFilterOptions());
    await findSelect(wrapper, 'fine-die-count-select').vm.$emit('update:modelValue', ['2', '4']);
    expect(fineFilter.die_count).toEqual(['2', '4']);
    expect(wrapper.emitted('change')).toBeTruthy();
  });

  it('changing 打線數 emits change and mutates fineFilter.wire_count (mirrors Package/Type wiring)', async () => {
    const fineFilter = makeFineFilter();
    const wrapper = mountFineFilterBar(fineFilter, makeFilterOptions());
    await findSelect(wrapper, 'fine-wire-count-select').vm.$emit('update:modelValue', ['8']);
    expect(fineFilter.wire_count).toEqual(['8']);
    expect(wrapper.emitted('change')).toBeTruthy();
  });

  it('changing Package still emits change and mutates fineFilter.package (existing behavior unchanged)', async () => {
    const fineFilter = makeFineFilter();
    const wrapper = mountFineFilterBar(fineFilter, makeFilterOptions());
    await findSelect(wrapper, 'fine-package-select').vm.$emit('update:modelValue', ['PKG-A']);
    expect(fineFilter.package).toEqual(['PKG-A']);
    expect(wrapper.emitted('change')).toBeTruthy();
  });
});
