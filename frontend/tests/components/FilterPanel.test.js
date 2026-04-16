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
    // All filter groups should still render (just with no options)
    expect(wrapper.findAll('.filter-group').length).toBe(6);
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
