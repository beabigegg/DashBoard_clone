// @vitest-environment jsdom

import { describe, expect, it } from 'vitest';
import { shallowMount } from '@vue/test-utils';

import FineFilterBar from '../../src/eap-alarm/FineFilterBar.vue';
import TrendChart from '../../src/eap-alarm/TrendChart.vue';

const emptyFineFilter = {
  alarm_text: [],
  eqp_id: [],
  lot_id: [],
  pj_type: [],
  product_line: [],
  pj_bop: [],
};

const emptyFilterOptions = {
  alarm_text_options: [],
  equipment_id_options: [],
  lot_id_options: [],
  pj_type_options: [],
  product_line_options: [],
  pj_bop_options: [],
};

describe('EAP ALARM normalized display labels', () => {
  it('uses Type, Package, and BOP in the fine filters', () => {
    const wrapper = shallowMount(FineFilterBar, {
      props: {
        fineFilter: structuredClone(emptyFineFilter),
        filterOptions: structuredClone(emptyFilterOptions),
      },
    });

    const labels = wrapper.findAll('.filter-label').map((label) => label.text());
    expect(labels).toEqual(['ALARM 訊息', '機台 ID', 'LOT ID', 'Type', 'Package', 'BOP']);
    expect(wrapper.html()).toContain('placeholder="全部 Type"');
  });

  it('uses the same product dimension labels in the trend controls', () => {
    const wrapper = shallowMount(TrendChart, {
      props: { labels: [], series: [], granularity: 'day', groupBy: 'alarm_text' },
    });

    const labels = wrapper
      .findAll('[data-testid="trend-group-by-toggle"] button')
      .map((button) => button.text());
    expect(labels).toEqual(['ALARM 訊息', '機台', 'LOT', 'Type', 'Package', 'BOP']);
  });
});
