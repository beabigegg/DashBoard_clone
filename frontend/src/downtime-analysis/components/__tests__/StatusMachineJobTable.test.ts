// @vitest-environment jsdom
/**
 * StatusMachineJobTable component tests
 * TDD — written before the component exists.
 * Change: downtime-analysis-page-redesign (IP-10)
 */

import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';

// Will exist after IP-6 is implemented
import StatusMachineJobTable from '../StatusMachineJobTable.vue';
import type { EquipmentDetailRow, ChartFilter, TierThreeEntry, DowntimeKpiShape } from '../../types';

function makeEquipmentRow(override: Partial<EquipmentDetailRow> = {}): EquipmentDetailRow {
  return {
    resource_id: 'R-001',
    resource_name: 'Machine A',
    workcenter: 'WC-SMT',
    family: 'F-001',
    udt_hours: 5.0,
    sdt_hours: 2.0,
    egt_hours: 1.0,
    total_hours: 8.0,
    event_count: 3,
    udt_event_count: 2,
    sdt_event_count: 1,
    egt_event_count: 0,
    top_reason: 'EE Repair',
    ...override,
  };
}

const defaultChartFilter: ChartFilter = { big_category: null, status_types: null };
const defaultSummary: DowntimeKpiShape = {
  total_hours: 10, udt_hours: 5, sdt_hours: 3, egt_hours: 2, event_count: 5, avg_event_min: 120,
};

describe('StatusMachineJobTable', () => {
  it('renders Tier 1 status group rows from props', async () => {
    const rows = [makeEquipmentRow()];
    const wrapper = mount(StatusMachineJobTable, {
      props: {
        equipmentRows: rows,
        summaryData: defaultSummary,
        tierThreeCache: {},
        chartFilter: defaultChartFilter,
        loading: false,
        exporting: false,
      },
    });
    await nextTick();
    // All three status groups should be present as Tier 1 rows
    expect(wrapper.find('.status-group-row').exists()).toBe(true);
    const groupRows = wrapper.findAll('.status-group-row');
    expect(groupRows.length).toBe(3); // UDT, SDT, EGT
  });

  it('expands Tier 1 row to show Tier 2 machine rows', async () => {
    const rows = [makeEquipmentRow({ resource_id: 'R-001', udt_hours: 5.0 })];
    const wrapper = mount(StatusMachineJobTable, {
      props: {
        equipmentRows: rows,
        summaryData: defaultSummary,
        tierThreeCache: {},
        chartFilter: defaultChartFilter,
        loading: false,
        exporting: false,
      },
    });
    await nextTick();

    // Click the UDT group row to expand
    const groupRows = wrapper.findAll('.status-group-row');
    const udtRow = groupRows.find(r => r.text().includes('UDT'));
    expect(udtRow).toBeDefined();
    await udtRow!.trigger('click');
    await nextTick();

    // Machine rows should now be visible
    expect(wrapper.find('.machine-row').exists()).toBe(true);
    expect(wrapper.find('.machine-row').text()).toContain('Machine A');
  });

  it('collapses expanded Tier 1 row on second click', async () => {
    const rows = [makeEquipmentRow()];
    const wrapper = mount(StatusMachineJobTable, {
      props: {
        equipmentRows: rows,
        summaryData: defaultSummary,
        tierThreeCache: {},
        chartFilter: defaultChartFilter,
        loading: false,
        exporting: false,
      },
    });
    await nextTick();

    const groupRows = wrapper.findAll('.status-group-row');
    const udtRow = groupRows.find(r => r.text().includes('UDT'));
    expect(udtRow).toBeDefined();

    // First click: expand
    await udtRow!.trigger('click');
    await nextTick();
    expect(wrapper.find('.machine-row').exists()).toBe(true);

    // Second click: collapse
    await udtRow!.trigger('click');
    await nextTick();
    expect(wrapper.find('.machine-row').exists()).toBe(false);
  });

  it('emits expand-machine with resource_id and status_type when Tier 2 row expanded', async () => {
    const rows = [makeEquipmentRow({ resource_id: 'R-001', udt_hours: 5.0 })];
    const tierThreeCache: Record<string, TierThreeEntry> = {};
    const wrapper = mount(StatusMachineJobTable, {
      props: {
        equipmentRows: rows,
        summaryData: defaultSummary,
        tierThreeCache,
        chartFilter: defaultChartFilter,
        loading: false,
        exporting: false,
      },
    });
    await nextTick();

    // Expand Tier 1 UDT group
    const udtRow = wrapper.findAll('.status-group-row').find(r => r.text().includes('UDT'));
    await udtRow!.trigger('click');
    await nextTick();

    // Expand Tier 2 machine row
    const machineRow = wrapper.find('.machine-row');
    await machineRow.trigger('click');
    await nextTick();

    // MachineEventRows mounts -> emits 'mount' -> parent emits 'expand-machine'
    // The expand-machine event should fire with resourceId and statusType
    const expandEvents = wrapper.emitted('expand-machine');
    expect(expandEvents).toBeDefined();
    if (expandEvents) {
      expect(expandEvents[0][0]).toMatchObject({ resourceId: 'R-001', statusType: 'UDT' });
    }
  });

  it('empty status_types array shows all three status groups (B-1 fix)', async () => {
    const rows = [makeEquipmentRow()];
    const wrapper = mount(StatusMachineJobTable, {
      props: {
        equipmentRows: rows,
        summaryData: defaultSummary,
        tierThreeCache: {},
        chartFilter: { big_category: null, status_types: [] },
        loading: false,
        exporting: false,
      },
    });
    await nextTick();
    // Empty array must behave as "no filter" — all three groups visible
    const groupRows = wrapper.findAll('.status-group-row');
    expect(groupRows.length).toBe(3);
  });

  it('chartFilter status_types prop shows only matching status groups', async () => {
    const rows = [
      makeEquipmentRow({ resource_id: 'R-001', udt_hours: 5.0, sdt_hours: 0, egt_hours: 0 }),
      makeEquipmentRow({ resource_id: 'R-002', sdt_hours: 3.0, udt_hours: 0, egt_hours: 0 }),
    ];
    const wrapper = mount(StatusMachineJobTable, {
      props: {
        equipmentRows: rows,
        summaryData: defaultSummary,
        tierThreeCache: {},
        chartFilter: { big_category: null, status_types: ['UDT'] },
        loading: false,
        exporting: false,
      },
    });
    await nextTick();

    // With status_types=['UDT'], only UDT group should be shown
    const groupRows = wrapper.findAll('.status-group-row');
    expect(groupRows.length).toBe(1);
    expect(groupRows[0].text()).toContain('UDT');
  });
});
