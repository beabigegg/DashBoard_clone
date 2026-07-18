// @vitest-environment jsdom
/**
 * PlanAchievementStackedChart — unit tests.
 *
 * DailyView-only chart (x-axis = PACKAGE_LF groups; D班/N班 render as SEPARATE
 * side-by-side grouped bars — NOT stacked; CumulativeView's own trend chart is
 * CumulativeTrendComboChart.vue). Y-axis is 達成率 (%) — a SINGLE axis; 計畫 is
 * the y=100 markLine, never a second scale (dual y-axis is a dataviz
 * anti-pattern). The bars share NO `stack` key, so each shift's bar
 * independently exceeds/falls short of 100% (班達成率 per shift).
 *
 * Field-directed display spec: each bar's DIRECT label is percent-only — e.g.
 * "75.0%"; the underlying quantity moves to the tooltip ("% (量)" per shift).
 * A 0%-tall bar still renders its "0.0%" label at the baseline. Colors are
 * resolved via `resolveCssVar()` (CSS custom properties), never inline `rgb()`
 * literals — mirrors resource-history/components/StackedChart.vue's
 * established convention (css-contract.md §2.4 chart exception).
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

  it('maps each series prop to a SEPARATE (non-stacked) grouped bar — no shared stack key', () => {
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
    // NO stack key on any bar series -- ECharts groups un-stacked bars
    // side-by-side per category, so D班/N班 read as two independent bars.
    barSeries.forEach((s) => expect(s.stack).toBeUndefined());
    barSeries.forEach((s) => expect(s).not.toHaveProperty('stackStrategy'));
  });

  it('each bar keeps its OWN value (never summed/normalized) — a shift CAN exceed 100% on its own bar', () => {
    const wrapper = mountChart({
      categories: ['OVER'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [140] }, // over-plan shift
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [60] },
      ],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const barSeries = series.filter((s) => s.type === 'bar');
    // Values pass through untouched — D班's own bar is 140, not clamped to 100
    // and not re-based against N班.
    expect((barSeries[0].data as number[])[0]).toBe(140);
    expect((barSeries[1].data as number[])[0]).toBe(60);
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

  it('attaches a markLine at y=100 labeled 計畫 across the plot (single axis, not a second scale)', () => {
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

  it('EVERY bar (D班 AND N班) gets its own percent-only direct label — quantity moves to the tooltip', () => {
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
    // Percent-only on the bar (no "(量)") — the quantity is in the tooltip.
    expect(dLabel({ dataIndex: 0 })).toBe('75.0%');
    expect(nLabel({ dataIndex: 0 })).toBe('25.0%');
  });

  it('grouped bars carry no per-series label offset — side-by-side placement already separates D班/N班 labels', () => {
    const wrapper = mountChart({
      categories: ['DO-218AB'],
      series: [
        { name: 'D班', colorVar: 'var(--pa-shift-d)', data: [null], qtyData: [172400] },
        { name: 'N班', colorVar: 'var(--pa-shift-n)', data: [null], qtyData: [0] },
      ],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    // No stacking → no baseline collision to dodge → no `offset` hack needed;
    // each label anchors above its own side-by-side bar.
    expect((series[0].label as Record<string, unknown>).offset).toBeUndefined();
    expect((series[1].label as Record<string, unknown>).offset).toBeUndefined();
  });

  it('a 0%-tall bar (no 計畫 configured yet) still renders its "0.0%" label at the baseline', () => {
    const wrapper = mountChart({
      categories: ['DO-218AB'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [null], qtyData: [2420] }],
    });
    const option = getOption(wrapper);
    const series = option.series as Array<Record<string, unknown>>;
    const label = (series[0].label as { formatter: (p: { dataIndex: number }) => string }).formatter;
    expect(label({ dataIndex: 0 })).toBe('0.0%');
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
