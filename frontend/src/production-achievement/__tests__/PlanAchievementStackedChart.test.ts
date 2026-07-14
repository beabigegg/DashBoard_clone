// @vitest-environment jsdom
/**
 * PlanAchievementStackedChart — unit tests (TDD, production-achievement
 * -overhaul IP-8).
 *
 * Shared chart for BOTH DailyView (x-axis = PACKAGE_LF groups, D%/N% stacked
 * series) and CumulativeView-trend (x-axis = dates, one aggregate-rate
 * series). Must be a REAL stacked series (regular `stack`, never ECharts'
 * normalize-to-100 mode) so a segment CAN visually exceed 100% for an
 * over-plan combination — a normalize-to-100 stack would silently cap that.
 * A `markLine` at y=100 labeled 計畫 is always present. Colors are resolved
 * via `resolveCssVar()` (CSS custom properties), never inline `rgb()`
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

  it('attaches a markLine at y=100 labeled 計畫 to the stacked series', () => {
    const wrapper = mountChart({
      categories: ['A'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [80] }],
    });
    const option = getOption(wrapper);
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

  it('shares one component for both x-axis shapes: PACKAGE_LF groups (daily) and dates (cumulative trend)', () => {
    const dailyWrapper = mountChart({
      categories: ['SOD-123FL', 'TO-277(B)'],
      series: [{ name: 'D班', colorVar: 'var(--pa-shift-d)', data: [70, 40] }],
    });
    const dailyOption = getOption(dailyWrapper);
    expect((dailyOption.xAxis as { data: string[] }).data).toEqual(['SOD-123FL', 'TO-277(B)']);

    const cumulativeWrapper = mountChart({
      categories: ['2026-07-01', '2026-07-02'],
      series: [{ name: '達成率', colorVar: 'var(--pa-cumulative-rate)', data: [95, 102] }],
    });
    const cumulativeOption = getOption(cumulativeWrapper);
    expect((cumulativeOption.xAxis as { data: string[] }).data).toEqual(['2026-07-01', '2026-07-02']);
  });
});
