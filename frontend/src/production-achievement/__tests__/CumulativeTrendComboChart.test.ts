// @vitest-environment jsdom
/**
 * CumulativeTrendComboChart — unit tests.
 *
 * 當月/自訂區間 trend chart: x-axis = date, left y-axis = bar (每日產出數量,
 * that day's own actual output), right y-axis = line (累計達成率, the RUNNING
 * cumulative rate through that day). A DELIBERATE dual y-axis (two different
 * -unit measures sharing a date axis), mirroring the codebase's existing
 * eap-alarm/ParetoChart.vue bar+累積% combo pattern.
 *
 * The `option` passed to <VChart> is asserted via the stubbed child
 * component's received prop, same convention as PlanAchievementStackedChart.test.ts.
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import CumulativeTrendComboChart from '../components/CumulativeTrendComboChart.vue';

const VChartStub = vi.hoisted(() => ({
  name: 'VChart',
  props: ['option', 'autoresize'],
  template: '<div class="vchart-stub" />',
}));

vi.mock('vue-echarts', () => ({ default: VChartStub }));

function mountChart(props: Record<string, unknown>) {
  return mount(CumulativeTrendComboChart, { props });
}

function getOption(wrapper: ReturnType<typeof mountChart>): Record<string, unknown> {
  return wrapper.findComponent(VChartStub).props('option') as Record<string, unknown>;
}

describe('CumulativeTrendComboChart', () => {
  it('renders the empty state when there are no categories', () => {
    const wrapper = mountChart({ categories: [] });
    expect(wrapper.find('[data-testid="pa-combo-chart-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-combo-chart"]').exists()).toBe(false);
  });

  it('builds a bar series (每日產出數量) on the left axis and a line series (累計達成率) on the right axis', () => {
    const wrapper = mountChart({
      categories: ['2026-07-01', '2026-07-02'],
      qtyData: [100, 150],
      rateData: [83.3, 104.2],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const bar = series.find((s) => s.type === 'bar')!;
    const line = series.find((s) => s.type === 'line')!;
    expect(bar.yAxisIndex).toBe(0);
    expect(bar.data).toEqual([100, 150]);
    expect(line.yAxisIndex).toBe(1);
    expect(line.data).toEqual([83.3, 104.2]);
  });

  it('exposes exactly two y-axes: left = 每日產出數量 (qty), right = 累計達成率 (%)', () => {
    const wrapper = mountChart({ categories: ['2026-07-01'], qtyData: [100], rateData: [90] });
    const option = getOption(wrapper);
    const yAxis = option.yAxis as Array<Record<string, unknown>>;
    expect(yAxis).toHaveLength(2);
    expect(yAxis[0].position).toBe('left');
    expect(yAxis[0].name).toContain('每日產出數量');
    expect(yAxis[1].position).toBe('right');
    expect(yAxis[1].name).toContain('累計達成率');
  });

  it('the x-axis category data is the date list, unmodified', () => {
    const wrapper = mountChart({ categories: ['2026-07-01', '2026-07-02', '2026-07-03'], qtyData: [1, 2, 3], rateData: [10, 20, 30] });
    const option = getOption(wrapper);
    expect((option.xAxis as { data: string[] }).data).toEqual(['2026-07-01', '2026-07-02', '2026-07-03']);
  });

  it('null/undefined qty values degrade to 0 bar height, never NaN', () => {
    const wrapper = mountChart({ categories: ['A'], qtyData: [null], rateData: [50] });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const bar = series.find((s) => s.type === 'bar')!;
    expect((bar.data as number[])[0]).toBe(0);
  });

  it('null/undefined rate values stay null on the line (a gap, not a false 0%) and connectNulls bridges the gap visually', () => {
    const wrapper = mountChart({ categories: ['A', 'B', 'C'], qtyData: [1, 2, 3], rateData: [50, null, 70] });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const line = series.find((s) => s.type === 'line')!;
    expect((line.data as (number | null)[])[1]).toBeNull();
    expect(line.connectNulls).toBe(true);
  });

  it('attaches a y=100 計畫 markLine to the line series (on the right/rate axis, not the qty axis)', () => {
    const wrapper = mountChart({ categories: ['A'], qtyData: [100], rateData: [90] });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const line = series.find((s) => s.type === 'line')!;
    const markLine = line.markLine as { data: Array<{ yAxis: number }>; label: { formatter: string } };
    expect(markLine.data[0].yAxis).toBe(100);
    expect(markLine.label.formatter).toContain('計畫');
    const bar = series.find((s) => s.type === 'bar')!;
    expect(bar.markLine).toBeUndefined();
  });

  it('resolves series colors via resolveCssVar() (var(--x) indirection), never a raw inline rgb()/hex literal', () => {
    const wrapper = mountChart({ categories: ['A'], qtyData: [100], rateData: [90] });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const barColor = (series.find((s) => s.type === 'bar')!.itemStyle as { color: string }).color;
    const lineColor = (series.find((s) => s.type === 'line')!.lineStyle as { color: string }).color;
    for (const color of [barColor, lineColor]) {
      expect(color).not.toMatch(/^rgb\(/);
      expect(color).not.toMatch(/^#[0-9a-f]{3,6}$/i);
    }
  });

  it('tooltip formats the qty series as an integer quantity and the rate series as a percentage, both per-date', () => {
    const wrapper = mountChart({ categories: ['2026-07-01'], qtyData: [1234], rateData: [83.3] });
    const option = getOption(wrapper);
    const tooltip = option.tooltip as { formatter: (params: unknown) => string };
    const html = tooltip.formatter([
      { marker: '', seriesName: '每日產出數量', seriesIndex: 0, dataIndex: 0, value: 1234, axisValueLabel: '2026-07-01' },
      { marker: '', seriesName: '累計達成率', seriesIndex: 1, dataIndex: 0, value: 83.3, axisValueLabel: '2026-07-01' },
    ]);
    expect(html).toContain('2026-07-01');
    expect(html).toContain('1,234');
    expect(html).toContain('83.3%');
  });

  it('tooltip renders "—" for a null rate value instead of "null%" or "NaN%"', () => {
    const wrapper = mountChart({ categories: ['A'], qtyData: [1], rateData: [null] });
    const option = getOption(wrapper);
    const tooltip = option.tooltip as { formatter: (params: unknown) => string };
    const html = tooltip.formatter([{ marker: '', seriesName: '累計達成率', seriesIndex: 1, dataIndex: 0, value: null, axisValueLabel: 'A' }]);
    expect(html).toContain('—');
    expect(html).not.toContain('null%');
    expect(html).not.toContain('NaN%');
  });
});
