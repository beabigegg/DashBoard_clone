// @vitest-environment jsdom

import { describe, expect, it } from 'vitest';
import { shallowMount } from '@vue/test-utils';
import VChart from 'vue-echarts';

import ParetoChart from '../../src/eap-alarm/ParetoChart.vue';

function makeItems(count) {
  return Array.from({ length: count }, (_, index) => ({
    name: `ALARM-${String(index + 1).padStart(2, '0')}`,
    count: count - index,
    cumulative_pct: ((index + 1) / count) * 100,
  }));
}

function mountChart(itemCount) {
  return shallowMount(ParetoChart, {
    props: {
      items: makeItems(itemCount),
      total: itemCount,
      dim: 'alarm_text',
      loading: false,
    },
  });
}

describe('EAP ALARM Pareto chart layout', () => {
  it('uses horizontal data zoom when categories exceed the visible limit', () => {
    const wrapper = mountChart(30);
    const option = wrapper.findComponent(VChart).props('option');

    expect(option.dataZoom).toHaveLength(2);
    expect(option.dataZoom[0].type).toBe('inside');
    expect(option.dataZoom[1].type).toBe('slider');
    expect(option.dataZoom[1].end).toBe(50);
    expect(option.grid.bottom).toBe(112);
  });

  it('keeps the legend above the plot and hides the slider for short lists', () => {
    const wrapper = mountChart(10);
    const option = wrapper.findComponent(VChart).props('option');

    expect(option.legend.top).toBe(0);
    expect(option.dataZoom).toEqual([]);
    expect(option.grid.bottom).toBe(82);
  });
});
