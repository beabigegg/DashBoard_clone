// @vitest-environment jsdom
/**
 * Component tests for TrendChart.vue's groupby button row (ctrl-trend-groupby).
 *
 * Validates:
 * - die_count/wire_count render as additional groupby buttons alongside the
 *   existing family/model/equipment_id/package buttons
 * - clicking a groupby button emits 'group-by-change' with that button's value
 *   (mirrors the existing family/model/equipment_id/package buttons)
 * - the active button (matching the `groupBy` prop) gets the primary style
 */
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';

import TrendChart from '../../src/uph-performance/TrendChart.vue';

function mountTrendChart(props = {}) {
  return mount(TrendChart, {
    props: { labels: [], series: [], groupBy: 'family', loading: false, ...props },
    global: {
      // vue-echarts renders a real canvas-backed component that doesn't play
      // well with jsdom; stub it out since these tests target the groupby
      // button row, not the chart canvas itself.
      stubs: { VChart: true },
    },
  });
}

function findGroupByButtons(wrapper) {
  return wrapper.find('[data-testid="ctrl-trend-groupby"]').findAll('button');
}

describe('TrendChart groupby buttons', () => {
  it('renders a button for every GROUP_BY_OPTIONS entry, including the new 晶粒數/打線數 axes', () => {
    const wrapper = mountTrendChart();
    const labels = findGroupByButtons(wrapper).map((b) => b.text());
    expect(labels).toEqual(['類別', '機型', '機台', 'Package', '晶粒數', '打線數']);
  });

  it('clicking the 晶粒數 button emits group-by-change with "die_count" (mirrors the existing buttons)', async () => {
    const wrapper = mountTrendChart();
    const button = findGroupByButtons(wrapper).find((b) => b.text() === '晶粒數');
    await button.trigger('click');
    expect(wrapper.emitted('group-by-change')).toBeTruthy();
    expect(wrapper.emitted('group-by-change')[0]).toEqual(['die_count']);
  });

  it('clicking the 打線數 button emits group-by-change with "wire_count" (mirrors the existing buttons)', async () => {
    const wrapper = mountTrendChart();
    const button = findGroupByButtons(wrapper).find((b) => b.text() === '打線數');
    await button.trigger('click');
    expect(wrapper.emitted('group-by-change')).toBeTruthy();
    expect(wrapper.emitted('group-by-change')[0]).toEqual(['wire_count']);
  });

  it('marks the button matching the groupBy prop as active (ui-btn--primary), including die_count/wire_count', () => {
    const dieCountActive = mountTrendChart({ groupBy: 'die_count' });
    const dieCountBtn = findGroupByButtons(dieCountActive).find((b) => b.text() === '晶粒數');
    expect(dieCountBtn.classes()).toContain('ui-btn--primary');

    const wireCountActive = mountTrendChart({ groupBy: 'wire_count' });
    const wireCountBtn = findGroupByButtons(wireCountActive).find((b) => b.text() === '打線數');
    expect(wireCountBtn.classes()).toContain('ui-btn--primary');
  });
});
