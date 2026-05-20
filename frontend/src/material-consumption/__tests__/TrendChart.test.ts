// @vitest-environment jsdom
/**
 * Unit tests for ConsumptionTrendChart.vue
 * Change: material-part-consumption
 *
 * AC-2: one line series per material_part, hard cap 20 series
 * Granularity control lives in FilterPanel only; trend chart has no granularity buttons.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import ConsumptionTrendChart from '../components/ConsumptionTrendChart.vue';

// Stub VChart (vue-echarts) — avoid canvas in jsdom
vi.mock('vue-echarts', () => ({
  default: defineComponent({
    name: 'VChart',
    props: ['option', 'autoresize'],
    template: '<div class="vchart-stub" :data-option="JSON.stringify(option)" />',
  }),
}));

// Stub all echarts/core use() registrations
vi.mock('echarts/core', () => ({ use: vi.fn() }));
vi.mock('echarts/charts', () => ({ LineChart: {} }));
vi.mock('echarts/components', () => ({
  GridComponent: {},
  LegendComponent: {},
  TooltipComponent: {},
}));
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }));

function makeTrendData(parts: string[]) {
  return parts.flatMap((part) => [
    { period: '2026-W01', material_part: part, total_consumed: 100 },
    { period: '2026-W02', material_part: part, total_consumed: 120 },
  ]);
}

function mountChart(props: Record<string, unknown> = {}) {
  return mount(ConsumptionTrendChart, {
    props: {
      trend: [],
      ...props,
    },
  });
}

describe('ConsumptionTrendChart', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders_one_series_per_material_part', async () => {
    const parts = ['PartA', 'PartB'];
    const wrapper = mountChart({ trend: makeTrendData(parts) });
    await nextTick();

    const stub = wrapper.find('.vchart-stub');
    expect(stub.exists()).toBe(true);
    const option = JSON.parse(stub.attributes('data-option') || '{}');
    expect(option.series).toHaveLength(2);
    const names = option.series.map((s: { name: string }) => s.name);
    expect(names).toContain('PartA');
    expect(names).toContain('PartB');
  });

  it('caps_at_20_series', async () => {
    // 21 parts — chart should only emit 20 series
    const parts = Array.from({ length: 21 }, (_, i) => `Part${i + 1}`);
    const wrapper = mountChart({ trend: makeTrendData(parts) });
    await nextTick();

    const stub = wrapper.find('.vchart-stub');
    const option = JSON.parse(stub.attributes('data-option') || '{}');
    expect(option.series.length).toBe(20);
  });

  it('no_granularity_buttons_in_trend_chart', async () => {
    // Granularity control moved to FilterPanel; trend chart must not render any granularity buttons
    const wrapper = mountChart({ trend: makeTrendData(['PartA']) });
    await nextTick();

    expect(wrapper.find('[data-granularity]').exists()).toBe(false);
    expect(wrapper.find('.granularity-btn').exists()).toBe(false);
  });

  it('shows_empty_state_when_no_data', async () => {
    const wrapper = mountChart({ trend: [] });
    await nextTick();

    expect(wrapper.find('.chart-empty').exists()).toBe(true);
    expect(wrapper.find('.vchart-stub').exists()).toBe(false);
  });
});
