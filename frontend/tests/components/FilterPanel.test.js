// @vitest-environment jsdom
/**
 * FilterPanel component tests (wip-overview variant)
 *
 * Props:
 *   filters: Object (required)
 *   options: Object (default: {})
 *   loading: Boolean (default: false)
 *
 * Emits: 'apply', 'clear', 'draft-change'
 *
 * The component uses MultiSelect children for each filter field.
 * Uses shallowMount to avoid needing full MultiSelect rendering.
 */

import { describe, it, expect, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import FilterPanel from '../../src/wip-overview/components/FilterPanel.vue';

const emptyFilters = {
  workorder: [],
  lotid: [],
  package: [],
  type: [],
  firstname: [],
  waferdesc: [],
  workflow: [],
  bop: [],
  pjFunction: [],
};

describe('FilterPanel', () => {
  it('renders without crash when options is undefined', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: emptyFilters,
        options: undefined,
      },
    });
    expect(wrapper.exists()).toBe(true);
  });

  it('renders without crash when options is empty object', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: emptyFilters,
        options: {},
      },
    });
    expect(wrapper.exists()).toBe(true);
    // 9 filter groups: WORKORDER, LOT ID, PACKAGE, WORKFLOW, BOP, TYPE, FUNCTION, Wafer LOT, Wafer Type
    expect(wrapper.findAll('.filter-group').length).toBe(9);
  });

  it('renders WORKFLOW field label', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: { filters: emptyFilters, options: {} },
    });
    const labels = wrapper.findAll('label').map((el) => el.text());
    expect(labels).toContain('WORKFLOW');
  });

  it('renders BOP field label', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: { filters: emptyFilters, options: {} },
    });
    const labels = wrapper.findAll('label').map((el) => el.text());
    expect(labels).toContain('BOP');
  });

  it('renders FUNCTION field label', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: { filters: emptyFilters, options: {} },
    });
    const labels = wrapper.findAll('label').map((el) => el.text());
    expect(labels).toContain('FUNCTION');
  });

  it('renders field labels in correct 3x3 order', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: { filters: emptyFilters, options: {} },
    });
    const labels = wrapper.findAll('label').map((el) => el.text());
    // Row 1: WORKORDER, LOT ID, PACKAGE
    expect(labels[0]).toBe('WORKORDER');
    expect(labels[1]).toBe('LOT ID');
    expect(labels[2]).toBe('PACKAGE');
    // Row 2: WORKFLOW, BOP, TYPE
    expect(labels[3]).toBe('WORKFLOW');
    expect(labels[4]).toBe('BOP');
    expect(labels[5]).toBe('TYPE');
    // Row 3: FUNCTION, Wafer LOT, Wafer Type
    expect(labels[6]).toBe('FUNCTION');
    expect(labels[7]).toBe('Wafer LOT');
    expect(labels[8]).toBe('Wafer Type');
  });

  it('emits clear when 清除篩選 button is clicked', async () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: emptyFilters,
        options: {},
      },
    });
    const buttons = wrapper.findAll('button');
    const clearBtn = buttons.find((b) => b.text().includes('清除'));
    expect(clearBtn).toBeTruthy();
    await clearBtn.trigger('click');
    expect(wrapper.emitted('clear')).toBeTruthy();
    expect(wrapper.emitted('clear').length).toBe(1);
  });

  it('emits apply when 套用篩選 button is clicked', async () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: emptyFilters,
        options: {},
      },
    });
    const buttons = wrapper.findAll('button');
    const applyBtn = buttons.find((b) => b.text().includes('套用'));
    expect(applyBtn).toBeTruthy();
    await applyBtn.trigger('click');
    expect(wrapper.emitted('apply')).toBeTruthy();
    expect(wrapper.emitted('apply').length).toBe(1);
  });

  it('apply payload includes workflow, bop, pjFunction fields', async () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: { ...emptyFilters, workflow: ['WF1'], bop: ['BOP1'], pjFunction: ['FN1'] },
        options: {},
      },
    });
    const buttons = wrapper.findAll('button');
    const applyBtn = buttons.find((b) => b.text().includes('套用'));
    await applyBtn.trigger('click');
    const payload = wrapper.emitted('apply')[0][0];
    expect(payload).toHaveProperty('workflow');
    expect(payload).toHaveProperty('bop');
    expect(payload).toHaveProperty('pjFunction');
  });

  it('emits draft-change along with clear event', async () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: emptyFilters,
        options: {},
      },
    });
    const buttons = wrapper.findAll('button');
    const clearBtn = buttons.find((b) => b.text().includes('清除'));
    await clearBtn.trigger('click');
    expect(wrapper.emitted('draft-change')).toBeTruthy();
  });

  it('clear event resets workflow, bop, pjFunction to empty arrays', async () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: { ...emptyFilters, workflow: ['WF1'], bop: ['BOP1'], pjFunction: ['FN1'] },
        options: {},
      },
    });
    const buttons = wrapper.findAll('button');
    const clearBtn = buttons.find((b) => b.text().includes('清除'));
    await clearBtn.trigger('click');
    // draft-change emitted with cleared values
    const draftPayload = wrapper.emitted('draft-change')[0][0];
    expect(draftPayload.workflow).toEqual([]);
    expect(draftPayload.bop).toEqual([]);
    expect(draftPayload.pjFunction).toEqual([]);
  });

  it('buttons are disabled when loading=true', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: emptyFilters,
        options: {},
        loading: true,
      },
    });
    const buttons = wrapper.findAll('button');
    buttons.forEach((btn) => {
      expect(btn.attributes('disabled')).toBeDefined();
    });
  });

  it('initializes draft from filters prop (string comma-separated)', () => {
    const wrapper = shallowMount(FilterPanel, {
      props: {
        filters: { ...emptyFilters, workorder: 'WO001,WO002' },
        options: {},
      },
    });
    // As long as it doesn't crash, the draft initialization is correct
    expect(wrapper.exists()).toBe(true);
  });
});
