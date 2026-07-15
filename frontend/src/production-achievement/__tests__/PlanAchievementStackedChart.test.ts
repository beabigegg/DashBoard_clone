// @vitest-environment jsdom
/**
 * PlanAchievementStackedChart — unit tests.
 *
 * DailyView-only chart (x-axis = PACKAGE_LF groups, D%/N% stacked series;
 * CumulativeView's own trend chart is CumulativeTrendComboChart.vue). Y-axis
 * is 達成率 (%) — a SINGLE axis; 計畫 is the y=100 markLine,
 * never a second scale (dual y-axis is a dataviz anti-pattern). Must be a
 * REAL stacked series (regular `stack`, never ECharts' normalize-to-100
 * mode) so a segment CAN visually exceed 100% for an over-plan combination.
 *
 * Field-directed display spec: every value renders as "「%」(「量」)" — e.g.
 * "75.0% (300)" — as a DIRECT LABEL on each D/N segment (not tooltip-only),
 * which also means the quantity stays visible even when a segment is 0%
 * tall (no 計畫 configured yet). Colors are resolved via `resolveCssVar()`
 * (CSS custom properties), never inline `rgb()` literals — mirrors
 * resource-history/components/StackedChart.vue's established convention
 * (css-contract.md §2.4 chart exception).
 *
 * The `option` passed to <VChart> is asserted via the stubbed child
 * component's received prop (standard Vue Test Utils pattern) rather than
 * reaching into <script setup> internals.
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import PlanAchievementStackedChart from '../components/PlanAchievementStackedChart.vue';

const VChartStub = vi.hoisted(() => ({
  name: 'VChart',
  props: ['option', 'autoresize'],
  template: '<div class="vchart-stub" />',
}));

vi.mock('vue-echarts', () => ({ default: VChartStub }));

function mountChart(props: Record<string, unknown>) {
  return mount(PlanAchievementStackedChart, { props });
}

function getOption(wrapper: ReturnType<typeof mountChart>): Record<string, unknown> {
  return wrapper.findComponent(VChartStub).props('option') as Record<string, unknown>;
}

describe('PlanAchievementStackedChart', () => {
  it('renders the empty state when there are no categories', () => {
    const wrapper = mountChart({ categories: [], series: [] });
    expect(wrapper.find('[data-testid="pa-chart-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-chart"]').exists()).toBe(false);
  });

  it('maps each series prop to a REAL (non-normalized) stacked bar series sharing one stack key', () => {
    const wrapper = mountChart({
      categories: ['SOD-123FL', 'TO-277(B)'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [70, 40] },
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [45, 10] },
      ],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const barSeries = series.filter((s) => s.type === 'bar');
    expect(barSeries).toHaveLength(2);
    // Same non-empty stack key on every bar series -- and NOT ECharts' separate
    // percentage/normalize stacking API (no `stackStrategy`, no manual re-scale
    // to force each bar to sum to exactly 100).
    const stackKeys = new Set(barSeries.map((s) => s.stack));
    expect(stackKeys.size).toBe(1);
    expect([...stackKeys][0]).toBeTruthy();
    barSeries.forEach((s) => expect(s).not.toHaveProperty('stackStrategy'));
  });

  it('a segment CAN visually exceed 100% for an over-plan combination (values passed through untouched, never clamped)', () => {
    const wrapper = mountChart({
      categories: ['OVER'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [80] },
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [60] }, // 80 + 60 = 140% total
      ],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const total = series.filter((s) => s.type === 'bar').reduce((sum, s) => sum + ((s.data as number[])[0] || 0), 0);
    expect(total).toBe(140); // never clamped/normalized to 100
  });

  it('null values in a series data array degrade to 0 (no bar height), never NaN/Infinity', () => {
    const wrapper = mountChart({
      categories: ['A'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [null] }],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    expect((series[0].data as number[])[0]).toBe(0);
  });

  it('attaches a markLine at y=100 labeled 計畫 to the stacked series (single axis, not a second scale)', () => {
    const wrapper = mountChart({
      categories: ['A'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [80] }],
    });
    const option = getOption(wrapper);
    expect(Array.isArray(option.yAxis)).toBe(false);
    const series = option.series as Array<Record<string, unknown>>;
    const withMarkLine = series.find((s) => s.markLine);
    expect(withMarkLine).toBeDefined();
    const markLine = withMarkLine!.markLine as { data: Array<{ yAxis: number }>; label: { formatter: string } };
    expect(markLine.data[0].yAxis).toBe(100);
    expect(markLine.label.formatter).toContain('計畫');
  });

  it('resolves series colors via resolveCssVar() (a var(--x) expression), never a raw inline rgb() literal', () => {
    const wrapper = mountChart({
      categories: ['A'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [80] }],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const color = (series[0].itemStyle as { color: string }).color;
    // jsdom's getComputedStyle never resolves an unregistered custom property to
    // a real color, so resolveCssVar() legitimately falls through to '' here —
    // the structural guarantee under test is that no hardcoded rgb()/hex
    // literal was ever assigned as the series color.
    expect(color).not.toMatch(/^rgb\(/);
    expect(color).not.toMatch(/^#[0-9a-f]{3,6}$/i);
  });

  it('EVERY segment (D班 AND N班, not just the total) gets its own "% (QTY)" direct label — never tooltip-only', () => {
    const wrapper = mountChart({
      categories: ['SOD-123FL'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [75], qtyData: [300] },
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [25], qtyData: [100] },
      ],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const dLabel = (series[0].label as { show: boolean; formatter: (p: { dataIndex: number }) => string }).formatter;
    const nLabel = (series[1].label as { show: boolean; formatter: (p: { dataIndex: number }) => string }).formatter;
    expect((series[0].label as { show: boolean }).show).toBe(true);
    expect((series[1].label as { show: boolean }).show).toBe(true);
    expect(dLabel({ dataIndex: 0 })).toBe('75.0% (300)');
    expect(nLabel({ dataIndex: 0 })).toBe('25.0% (100)');
  });

  it('adjacent series get distinct label offsets so they never render on top of each other, even when both are 0% (no 計畫 configured — the field-reported garbled-text bug)', () => {
    const wrapper = mountChart({
      categories: ['DO-218AB'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [null], qtyData: [172400] },
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [null], qtyData: [0] },
      ],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const dOffset = (series[0].label as { offset: [number, number] }).offset;
    const nOffset = (series[1].label as { offset: [number, number] }).offset;
    // Same x anchor (both centered on the bar), but the y offset MUST differ —
    // that vertical gap is what keeps the two labels from literally
    // overlapping character-for-character when both segments tie at 0%.
    expect(dOffset[1]).not.toBe(nOffset[1]);
  });

  it('a 0%-tall segment (no 計畫 configured yet) still renders its "% (QTY)" label — the quantity stays visible', () => {
    const wrapper = mountChart({
      categories: ['DO-218AB'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [null], qtyData: [2420] }],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const label = (series[0].label as { formatter: (p: { dataIndex: number }) => string }).formatter;
    expect(label({ dataIndex: 0 })).toBe('0.0% (2,420)');
  });

  it('tooltip shows both the percentage AND the underlying quantity, per series', () => {
    const wrapper = mountChart({
      categories: ['SOD-123FL'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [75], qtyData: [300] },
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [25], qtyData: [100] },
      ],
    });
    const option = getOption(wrapper);
    const tooltip = option.tooltip as { formatter: (params: unknown) => string };
    const html = tooltip.formatter([
      { marker: '', seriesName: 'D班', seriesIndex: 0, dataIndex: 0, value: 75, axisValueLabel: 'SOD-123FL' },
      { marker: '', seriesName: 'N班', seriesIndex: 1, dataIndex: 0, value: 25, axisValueLabel: 'SOD-123FL' },
    ]);
    expect(html).toContain('75.0% (300)');
    expect(html).toContain('25.0% (100)');
  });

  it('tooltip degrades gracefully to "—" quantity when a series has no qtyData', () => {
    const wrapper = mountChart({
      categories: ['A'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [95] }],
    });
    const option = getOption(wrapper);
    const tooltip = option.tooltip as { formatter: (params: unknown) => string };
    const html = tooltip.formatter([{ marker: '', seriesName: 'D班', seriesIndex: 0, dataIndex: 0, value: 95, axisValueLabel: 'A' }]);
    expect(html).toContain('95.0%');
    expect(html).toContain('—');
  });

  it('x-axis category data comes straight from the categories prop (PACKAGE_LF groups)', () => {
    const wrapper = mountChart({
      categories: ['SOD-123FL', 'TO-277(B)'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [70, 40] }],
    });
    const option = getOption(wrapper);
    expect((option.xAxis as { data: string[] }).data).toEqual(['SOD-123FL', 'TO-277(B)']);
  });
});
