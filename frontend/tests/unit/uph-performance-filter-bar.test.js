// @vitest-environment jsdom
/**
 * Component tests for FilterBar.vue (redesigned coarse filter bar).
 *
 * Validates:
 * - canSubmit gates on date_from/date_to only (no at-least-one-of-N rule)
 * - 機型 / 工作站 / 機台 are cascading dropdowns from machine-options
 *   (DW_MES_RESOURCE): a dropdown's options are constrained by the UPSTREAM
 *   selections (family -> model -> workcenter -> equipment)
 * - changing an upstream axis PRUNES downstream selections no longer reachable
 * - handleClear resets every optional dim (incl. models) and emits clear
 * - machine-options / product-options failures render inline warnings while
 *   the rest of the bar stays usable
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
  // data-testid falls through to this root div (default inheritAttrs), so
  // findSelect() below can locate each dropdown by its testid.
  template: '<div class="multi-select-stub">{{ (modelValue || []).join(",") }}</div>',
});

const MACHINE_OPTIONS = {
  families: [
    { code: 'GDBA', label: 'Die-Bond' },
    { code: 'GWBA', label: 'Wire-Bond' },
  ],
  models: [
    { family: 'GDBA', model: 'DBA_AD832UR' },
    { family: 'GWBA', model: 'WBA_iHawk' },
  ],
  workcenters: ['焊接_DB', '焊接_WB'],
  equipment: [
    { equipment_id: 'GDBA-0001', family: 'GDBA', model: 'DBA_AD832UR', workcenter: '焊接_DB' },
    { equipment_id: 'GDBA-0002', family: 'GDBA', model: 'DBA_AD832UR', workcenter: '焊接_DB' },
    { equipment_id: 'GWBA-0003', family: 'GWBA', model: 'WBA_iHawk', workcenter: '焊接_WB' },
  ],
};

function makeFilters(overrides = {}) {
  return {
    date_from: '',
    date_to: '',
    families: [],
    models: [],
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
      machineOptions: MACHINE_OPTIONS,
      machineOptionsLoading: false,
      machineOptionsError: '',
      productFilterOptions: { pj_types: ['TYPE-A'], product_lines: ['PKG-A'] },
      loading: { querying: false },
      productOptionsLoading: false,
      productOptionsError: '',
      ...extraProps,
    },
    global: { stubs: { MultiSelect: MultiSelectStub } },
  });
}

function findSelect(wrapper, testid) {
  return wrapper
    .findAllComponents(MultiSelectStub)
    .find((c) => c.attributes('data-testid') === testid);
}

describe('FilterBar (redesigned)', () => {
  it('disables submit until both dates are filled (no at-least-one-of-N rule)', () => {
    const wrapper = mountFilterBar(makeFilters());
    expect(wrapper.find('[data-testid="ctrl-submit"]').attributes('disabled')).toBeDefined();
  });

  it('enables submit once both dates are set, with everything else empty', () => {
    const wrapper = mountFilterBar(makeFilters({ date_from: '2026-07-01', date_to: '2026-07-07' }));
    expect(wrapper.find('[data-testid="ctrl-submit"]').attributes('disabled')).toBeUndefined();
  });

  it('disables submit when date_from is after date_to', () => {
    const wrapper = mountFilterBar(makeFilters({ date_from: '2026-07-10', date_to: '2026-07-01' }));
    expect(wrapper.find('[data-testid="ctrl-submit"]').attributes('disabled')).toBeDefined();
  });

  it('機型 options are the real models (not GDBA/GWBA), constrained by the selected 類別', () => {
    // No family selected -> all models.
    const all = mountFilterBar(makeFilters());
    expect(findSelect(all, 'ctrl-model-select').props('options')).toEqual(['DBA_AD832UR', 'WBA_iHawk']);
    // Die-Bond selected -> only its models.
    const gdba = mountFilterBar(makeFilters({ families: ['GDBA'] }));
    expect(findSelect(gdba, 'ctrl-model-select').props('options')).toEqual(['DBA_AD832UR']);
  });

  it('機台 (equipment) is a dropdown constrained by family + model + workcenter', () => {
    const wrapper = mountFilterBar(makeFilters({ families: ['GDBA'], models: ['DBA_AD832UR'] }));
    expect(findSelect(wrapper, 'ctrl-equipment-select').props('options')).toEqual(['GDBA-0001', 'GDBA-0002']);
  });

  it('changing 類別 prunes downstream model/workcenter/equipment selections no longer reachable', async () => {
    const wrapper = mountFilterBar(
      makeFilters({
        families: ['GDBA'],
        models: ['DBA_AD832UR'],
        workcenter_names: ['焊接_DB'],
        equipment_ids: ['GDBA-0001'],
      }),
    );
    // Switch category to Wire-Bond: none of the Die-Bond downstream picks survive.
    await findSelect(wrapper, 'ctrl-family-select').vm.$emit('update:modelValue', ['GWBA']);
    const payload = wrapper.emitted('update:filters').slice(-1)[0][0];
    expect(payload.families).toEqual(['GWBA']);
    expect(payload.models).toEqual([]);
    expect(payload.workcenter_names).toEqual([]);
    expect(payload.equipment_ids).toEqual([]);
  });

  it('handleClear resets every optional dim (incl. models) and emits clear', async () => {
    const wrapper = mountFilterBar(
      makeFilters({
        date_from: '2026-07-01',
        date_to: '2026-07-07',
        families: ['GDBA'],
        models: ['DBA_AD832UR'],
        workcenter_names: ['焊接_DB'],
        equipment_ids: ['GDBA-0001'],
        packages: ['PKG-A'],
        pj_types: ['TYPE-A'],
      }),
    );
    await wrapper.find('[data-testid="ctrl-clear"]').trigger('click');
    const payload = wrapper.emitted('update:filters').slice(-1)[0][0];
    expect(payload.families).toEqual([]);
    expect(payload.models).toEqual([]);
    expect(payload.workcenter_names).toEqual([]);
    expect(payload.equipment_ids).toEqual([]);
    expect(payload.packages).toEqual([]);
    expect(payload.pj_types).toEqual([]);
    expect(wrapper.emitted('clear')).toBeTruthy();
  });

  it('shows the inline machine-options warning without disabling the date inputs (degrade)', () => {
    const wrapper = mountFilterBar(makeFilters(), { machineOptionsError: 'mock 500' });
    const warning = wrapper.find('[data-testid="machine-options-warning"]');
    expect(warning.exists()).toBe(true);
    expect(warning.text()).toContain('mock 500');
    expect(wrapper.find('[data-testid="start-date"]').attributes('disabled')).toBeUndefined();
  });

  it('shows the inline product-options warning (confirmed #6)', () => {
    const wrapper = mountFilterBar(makeFilters(), { productOptionsError: 'mock 500' });
    const warning = wrapper.find('[data-testid="product-options-warning"]');
    expect(warning.exists()).toBe(true);
    expect(warning.text()).toContain('mock 500');
  });

  it('the global Type filter (ctrl-type-select-global) is a distinct element from any ranking control', () => {
    const wrapper = mountFilterBar(makeFilters());
    expect(wrapper.find('[data-testid="ctrl-type-select-global"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="ctrl-ranking-type-filter"]').exists()).toBe(false);
  });
});
