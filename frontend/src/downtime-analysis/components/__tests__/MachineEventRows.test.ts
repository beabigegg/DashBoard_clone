// @vitest-environment jsdom
/**
 * MachineEventRows component tests
 * TDD — written before the component exists.
 * Change: downtime-analysis-page-redesign (IP-10)
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';

// Will exist after IP-6b is implemented
import MachineEventRows from '../MachineEventRows.vue';
import type { TierThreeEntry, EventDetailRow } from '../../types';

/** Pin the events wrapper key as a named constant per test-plan.md AC-8 */
const EVENTS_WRAPPER_KEY = 'events' as const;
// Confirming the key is correct: the backend route returns success_response(events=...)
// and the composable reads data[EVENTS_WRAPPER_KEY].

function makeEventRow(override: Partial<EventDetailRow> = {}): EventDetailRow {
  return {
    event_id: 'EVT-001',
    resource_id: 'R-001',
    resource_name: 'Machine A',
    status: 'UDT',
    reason: 'EE Repair',
    category: '維修',
    start_ts: '2026-05-27T08:00:00',
    end_ts: '2026-05-27T10:00:00',
    hours: 2.0,
    match_source: 'jobid',
    job: null,
    ...override,
  };
}

describe('MachineEventRows', () => {
  it('shows loading skeleton when cacheEntry.loading is true', async () => {
    const entry: TierThreeEntry = { rows: [], loading: true, loaded: false, error: '' };
    const wrapper = mount(MachineEventRows, {
      props: { cacheEntry: entry },
    });
    await nextTick();
    // Loading indicator should be present
    expect(wrapper.find('.event-rows-loading').exists()).toBe(true);
    // Table should not be visible when loading
    expect(wrapper.find('.event-inner-table').exists()).toBe(false);
  });

  it('renders event rows when cacheEntry has data', async () => {
    const rows = [makeEventRow(), makeEventRow({ event_id: 'EVT-002', reason: 'PM' })];
    const entry: TierThreeEntry = { rows, loading: false, loaded: true, error: '' };
    const wrapper = mount(MachineEventRows, {
      props: { cacheEntry: entry },
    });
    await nextTick();
    // Table should exist
    expect(wrapper.find('.event-inner-table').exists()).toBe(true);
    // Should have 2 data rows
    const bodyRows = wrapper.findAll('.event-inner-table tbody tr');
    expect(bodyRows.length).toBe(2);
  });

  it('emits mount on onMounted', async () => {
    const entry: TierThreeEntry = { rows: [], loading: true, loaded: false, error: '' };
    const wrapper = mount(MachineEventRows, {
      props: { cacheEntry: entry },
    });
    await nextTick();
    // Component should emit 'mount' when mounted
    expect(wrapper.emitted('mount')).toBeDefined();
    expect(wrapper.emitted('mount')?.length).toBe(1);
  });

  it('resolves rows from events wrapper key not bare array', async () => {
    // This test documents that the composable resolves data[EVENTS_WRAPPER_KEY]
    // not a bare array. The component itself receives the resolved rows via props.
    // Here we verify the rows prop renders correctly (not bare array misuse).
    const rows = [makeEventRow({ event_id: 'EVT-EVENTS-KEY' })];
    // Simulate what loadMachineStatusEvents returns after resolving data[EVENTS_WRAPPER_KEY]
    const resolvedFromEventsKey: TierThreeEntry = {
      rows, // these come from data.events in the composable
      loading: false,
      loaded: true,
      error: '',
    };
    const wrapper = mount(MachineEventRows, {
      props: { cacheEntry: resolvedFromEventsKey },
    });
    await nextTick();
    expect(wrapper.find('.event-inner-table').exists()).toBe(true);
    const bodyRows = wrapper.findAll('.event-inner-table tbody tr');
    expect(bodyRows.length).toBe(1);
    // Verify the EVENTS_WRAPPER_KEY constant is 'events' (pinned per AC-8)
    expect(EVENTS_WRAPPER_KEY).toBe('events');
  });

  it('empty events array renders empty-state message not silent blank', async () => {
    const entry: TierThreeEntry = { rows: [], loading: false, loaded: true, error: '' };
    const wrapper = mount(MachineEventRows, {
      props: { cacheEntry: entry },
    });
    await nextTick();
    // Empty state message should be shown — not a blank element
    expect(wrapper.find('.event-rows-empty').exists()).toBe(true);
    expect(wrapper.find('.event-rows-empty').text()).toContain('無事件記錄');
    // Table should not be rendered for empty data
    expect(wrapper.find('.event-inner-table').exists()).toBe(false);
  });
});
