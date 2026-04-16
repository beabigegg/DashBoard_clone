// @vitest-environment jsdom
/**
 * ParetoGrid component tests
 *
 * Props:
 *   paretoData: Object — keyed by dimension ('reason', 'package', 'type')
 *                        each value: { items: [...] }
 *   paretoSelections: Object
 *   loading: Boolean
 *   metricLabel: String
 *   selectedDates: Array
 *   displayScope: String
 *
 * Emits: 'item-toggle'
 *
 * ParetoGrid renders ParetoSection children (one per dimension).
 * Use shallowMount to isolate from ParetoSection complexity.
 */

import { describe, it, expect } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import ParetoGrid from '../../src/reject-history/components/ParetoGrid.vue';

describe('ParetoGrid', () => {
  it('renders without crash when paretoData is empty object', () => {
    const wrapper = shallowMount(ParetoGrid, {
      props: { paretoData: {} },
    });
    expect(wrapper.exists()).toBe(true);
    expect(wrapper.find('.pareto-grid').exists()).toBe(true);
  });

  it('renders without crash when paretoData is missing expected keys', () => {
    // Only has 'reason', missing 'package' and 'type'
    const wrapper = shallowMount(ParetoGrid, {
      props: {
        paretoData: {
          reason: { items: [{ value: 'Scratch', count: 10 }] },
        },
      },
    });
    expect(wrapper.exists()).toBe(true);
  });

  it('renders without crash when paretoData keys have no items array', () => {
    const wrapper = shallowMount(ParetoGrid, {
      props: {
        paretoData: {
          reason: {}, // missing items key
          package: null,
          type: undefined,
        },
      },
    });
    expect(wrapper.exists()).toBe(true);
  });

  it('renders three ParetoSection stubs (one per dimension)', () => {
    const wrapper = shallowMount(ParetoGrid, {
      props: {
        paretoData: {
          reason: { items: [] },
          package: { items: [] },
          type: { items: [] },
        },
      },
    });
    // shallowMount stubs child components — find stub elements
    const sections = wrapper.findAllComponents({ name: 'ParetoSection' });
    expect(sections.length).toBe(3);
  });

  it('emits item-toggle with dimension and value when ParetoSection triggers item-toggle', async () => {
    const wrapper = shallowMount(ParetoGrid, {
      props: {
        paretoData: {
          reason: { items: [{ value: 'Scratch', count: 5 }] },
          package: { items: [] },
          type: { items: [] },
        },
      },
    });
    // Trigger item-toggle from the first ParetoSection stub
    const sections = wrapper.findAllComponents({ name: 'ParetoSection' });
    await sections[0].vm.$emit('item-toggle', 'Scratch');
    expect(wrapper.emitted('item-toggle')).toBeTruthy();
    const [dimension, value] = wrapper.emitted('item-toggle')[0];
    expect(dimension).toBe('reason');
    expect(value).toBe('Scratch');
  });

  it('passes loading prop down to ParetoSection children', () => {
    const wrapper = shallowMount(ParetoGrid, {
      props: {
        paretoData: {},
        loading: true,
      },
    });
    const sections = wrapper.findAllComponents({ name: 'ParetoSection' });
    sections.forEach((section) => {
      expect(section.props('loading')).toBe(true);
    });
  });
});
