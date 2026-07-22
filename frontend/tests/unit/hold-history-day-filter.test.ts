// @vitest-environment jsdom
/**
 * Hold History — Daily Trend click-to-filter (dayFilter) unit coverage.
 *
 * Covers:
 *  - buildDayFilterCondition() (useHoldHistoryDuckDB.ts): SQL fragment generation
 *    for "YYYY-MM-DD:new" / "YYYY-MM-DD:release", plus malformed/empty input.
 *  - DailyTrend.vue: click on a Release/New Hold bar emits 'toggle-day' with the
 *    composite "date:type" value; clicks on non-bar series (or Future Hold) emit nothing.
 *  - App.vue-equivalent orchestrator wiring: clicking the same dayFilter value twice
 *    toggles committed.dayFilter back to ''.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';

import VChart from 'vue-echarts';

import { buildDayFilterCondition } from '../../src/hold-history/useHoldHistoryDuckDB';
import DailyTrend from '../../src/hold-history/components/DailyTrend.vue';
import { useFilterOrchestrator } from '../../src/shared-composables/useFilterOrchestrator';

// ── buildDayFilterCondition ───────────────────────────────────────────────────

describe('buildDayFilterCondition', () => {
  it('builds a HOLD_DAY/RN_HOLD_DAY clause for "YYYY-MM-DD:new"', () => {
    const clause = buildDayFilterCondition('2026-07-21:new');
    expect(clause).toContain('"HOLD_DAY"');
    expect(clause).toContain('"RN_HOLD_DAY"');
    expect(clause).toContain("DATE '2026-07-21'");
  });

  it('builds a RELEASE_DAY clause for "YYYY-MM-DD:release"', () => {
    const clause = buildDayFilterCondition('2026-07-21:release');
    expect(clause).toContain('"RELEASE_DAY"');
    expect(clause).toContain("DATE '2026-07-21'");
    expect(clause).not.toContain('HOLD_DAY');
  });

  it('returns null for empty/null input', () => {
    expect(buildDayFilterCondition('')).toBeNull();
    expect(buildDayFilterCondition(null)).toBeNull();
    expect(buildDayFilterCondition(undefined)).toBeNull();
  });

  it('returns null for a malformed date', () => {
    expect(buildDayFilterCondition('not-a-date:new')).toBeNull();
  });

  it('returns null for an unknown day type', () => {
    expect(buildDayFilterCondition('2026-07-21:bogus')).toBeNull();
  });

  it('returns null when missing the ":type" segment', () => {
    expect(buildDayFilterCondition('2026-07-21')).toBeNull();
  });
});

// ── DailyTrend.vue click-to-filter ────────────────────────────────────────────

const DAYS = [
  { date: '2026-07-20', releaseQty: 3, newHoldQty: 1, futureHoldQty: 0, holdQty: 5 },
  { date: '2026-07-21', releaseQty: 4, newHoldQty: 2, futureHoldQty: 1, holdQty: 6 },
];

// SectionCard is auto-stubbed by shallowMount by default, which swallows its
// slot content (including the nested VChart) — provide a slot-passthrough
// stub so the (auto-stubbed) VChart is still reachable via findComponent().
const SectionCardStub = {
  name: 'SectionCardStub',
  template: '<div><slot name="header" /><slot /></div>',
};

function mountDailyTrend(props = {}) {
  return shallowMount(DailyTrend, {
    props: { days: DAYS, ...props },
    global: { stubs: { SectionCard: SectionCardStub } },
  });
}

describe('DailyTrend.vue click-to-filter', () => {
  it('emits "toggle-day" with "<date>:release" when a Release bar is clicked', async () => {
    const wrapper = mountDailyTrend();
    const chart = wrapper.findComponent(VChart);
    await chart.vm.$emit('click', { seriesType: 'bar', seriesName: 'Release', dataIndex: 1 });

    const emitted = wrapper.emitted('toggle-day');
    expect(emitted).toBeTruthy();
    expect(emitted![0][0]).toBe('2026-07-21:release');
  });

  it('emits "toggle-day" with "<date>:new" when a New Hold bar is clicked', async () => {
    const wrapper = mountDailyTrend();
    const chart = wrapper.findComponent(VChart);
    await chart.vm.$emit('click', { seriesType: 'bar', seriesName: 'New Hold', dataIndex: 0 });

    const emitted = wrapper.emitted('toggle-day');
    expect(emitted).toBeTruthy();
    expect(emitted![0][0]).toBe('2026-07-20:new');
  });

  it('emits nothing for a line-series click (On Hold)', async () => {
    const wrapper = mountDailyTrend();
    const chart = wrapper.findComponent(VChart);
    await chart.vm.$emit('click', { seriesType: 'line', seriesName: 'On Hold', dataIndex: 0 });

    expect(wrapper.emitted('toggle-day')).toBeFalsy();
  });

  it('emits nothing for a Future Hold bar click (out of scope)', async () => {
    const wrapper = mountDailyTrend();
    const chart = wrapper.findComponent(VChart);
    await chart.vm.$emit('click', { seriesType: 'bar', seriesName: 'Future Hold', dataIndex: 0 });

    expect(wrapper.emitted('toggle-day')).toBeFalsy();
  });
});

// ── App.vue orchestrator wiring (dayFilter toggle) ────────────────────────────

describe('dayFilter orchestrator wiring (App.vue handleDayToggle equivalent)', () => {
  it('toggles committed.dayFilter off when the same value is clicked twice', () => {
    const orchestrator = useFilterOrchestrator({
      fields: {
        holdType: { trigger: 'immediate', initial: 'quality' },
        recordType: { trigger: 'immediate', initial: ['new'] },
        reasonFilter: { trigger: 'immediate', initial: '' },
        durationFilter: { trigger: 'immediate', initial: '' },
        dayFilter: { trigger: 'immediate', initial: '' },
      },
      dependencies: [
        { when: 'holdType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
        { when: 'holdType', then: ['dayFilter'], action: 'clear' },
        { when: 'recordType', then: ['reasonFilter', 'durationFilter'], action: 'clear' },
        { when: 'recordType', then: ['dayFilter'], action: 'clear' },
      ],
      urlSync: { enabled: false },
    });

    const committed = orchestrator.committed as { dayFilter: string };

    function handleDayToggle(value: string): void {
      const next = String(value || '').trim();
      if (!next) return;
      const current = committed.dayFilter;
      orchestrator.updateField('dayFilter', current === next ? '' : next);
    }

    expect(committed.dayFilter).toBe('');

    handleDayToggle('2026-07-21:new');
    expect(committed.dayFilter).toBe('2026-07-21:new');

    // Clicking the same bar again toggles the filter back off (additive, does not clear siblings)
    handleDayToggle('2026-07-21:new');
    expect(committed.dayFilter).toBe('');
  });

  it('switches to a different day/type without needing an explicit clear', () => {
    const orchestrator = useFilterOrchestrator({
      fields: {
        dayFilter: { trigger: 'immediate', initial: '' },
      },
      urlSync: { enabled: false },
    });
    const committed = orchestrator.committed as { dayFilter: string };

    function handleDayToggle(value: string): void {
      const next = String(value || '').trim();
      if (!next) return;
      const current = committed.dayFilter;
      orchestrator.updateField('dayFilter', current === next ? '' : next);
    }

    handleDayToggle('2026-07-20:release');
    expect(committed.dayFilter).toBe('2026-07-20:release');

    handleDayToggle('2026-07-21:new');
    expect(committed.dayFilter).toBe('2026-07-21:new');
  });
});

// ── DailyTrend.vue in-bar shimmer sweep ───────────────────────────────────────
// The active day-filter bar's itemStyle.color is a callback that returns an
// echarts LinearGradient (a bright band sweeping through the bar's own fill)
// for the matching dataIndex, and a plain flat color string otherwise.

interface ChartSeriesWithColorFn {
  name?: string;
  itemStyle?: { color?: (params: { dataIndex: number }) => unknown };
}

function findSeries(
  option: { series?: ChartSeriesWithColorFn[] },
  name: string,
): ChartSeriesWithColorFn | undefined {
  return (option?.series || []).find((s) => s.name === name);
}

describe('DailyTrend.vue day-filter shimmer sweep', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns a gradient (not a flat color) for the active bar while a day filter is active', async () => {
    vi.useFakeTimers();
    const wrapper = mountDailyTrend({ activeDayFilter: '2026-07-21:new' });

    // Half of SWEEP_PERIOD_MS (1400ms) — phase should be roughly mid-sweep,
    // though the exact value doesn't matter here, only that a gradient exists.
    await vi.advanceTimersByTimeAsync(700);

    const chart = wrapper.findComponent(VChart);
    const option = chart.props('option') as { series: ChartSeriesWithColorFn[] };
    const newHoldSeries = findSeries(option, 'New Hold');
    const colorFn = newHoldSeries?.itemStyle?.color;
    expect(colorFn).toBeTypeOf('function');

    // dataIndex 1 = '2026-07-21' in the DAYS fixture — the active bar.
    const activeColor = colorFn!({ dataIndex: 1 }) as { colorStops?: unknown[] };
    expect(activeColor).toBeTypeOf('object');
    expect(activeColor.colorStops).toBeTruthy();

    // A different bar on the same series stays the plain flat color.
    const inactiveColor = colorFn!({ dataIndex: 0 });
    expect(inactiveColor).toBe('rgb(220, 38, 38)');
  });

  it('keeps every bar a flat color when no day filter is active', () => {
    const wrapper = mountDailyTrend({ activeDayFilter: '' });
    const chart = wrapper.findComponent(VChart);
    const option = chart.props('option') as { series: ChartSeriesWithColorFn[] };
    const releaseSeries = findSeries(option, 'Release');
    const colorFn = releaseSeries?.itemStyle?.color;

    expect(colorFn!({ dataIndex: 0 })).toBe('rgb(22, 163, 74)');
    expect(colorFn!({ dataIndex: 1 })).toBe('rgb(22, 163, 74)');
  });

  it('tears down the sweep interval timer on unmount', () => {
    vi.useFakeTimers();
    const clearSpy = vi.spyOn(globalThis, 'clearInterval');
    const wrapper = mountDailyTrend({ activeDayFilter: '2026-07-21:new' });

    expect(() => wrapper.unmount()).not.toThrow();
    expect(clearSpy).toHaveBeenCalled();

    clearSpy.mockRestore();
  });
});
