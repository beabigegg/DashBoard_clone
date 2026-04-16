// @vitest-environment jsdom
/**
 * HoldMatrix component tests
 *
 * Props:
 *   data: Object — { workcenters, packages, matrix, workcenter_totals, package_totals, grand_total }
 *   activeFilter: Object — { workcenter?, package? }
 *
 * Emits: 'select'
 *
 * The matrix renders a table with workcenter rows and package columns.
 * The HoldMatrix is NOT a treemap — it is a cross-tab matrix table.
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import HoldMatrix from '../../src/hold-overview/components/HoldMatrix.vue';

const sampleData = {
  workcenters: ['WC-A', 'WC-B'],
  packages: ['PKG1', 'PKG2'],
  matrix: {
    'WC-A': { PKG1: 5, PKG2: 3 },
    'WC-B': { PKG1: 2, PKG2: 0 },
  },
  workcenter_totals: { 'WC-A': 8, 'WC-B': 2 },
  package_totals: { PKG1: 7, PKG2: 3 },
  grand_total: 10,
};

describe('HoldMatrix', () => {
  it('renders table when data has workcenters', () => {
    const wrapper = mount(HoldMatrix, {
      props: { data: sampleData },
    });
    expect(wrapper.find('table.hold-matrix-table').exists()).toBe(true);
  });

  it('renders placeholder when workcenters is empty', () => {
    const wrapper = mount(HoldMatrix, {
      props: { data: { workcenters: [], packages: [], matrix: {} } },
    });
    expect(wrapper.find('.placeholder').exists()).toBe(true);
    expect(wrapper.find('table').exists()).toBe(false);
  });

  it('renders placeholder when data is null', () => {
    const wrapper = mount(HoldMatrix, {
      props: { data: null },
    });
    expect(wrapper.find('.placeholder').exists()).toBe(true);
  });

  it('renders correct number of workcenter rows', () => {
    const wrapper = mount(HoldMatrix, {
      props: { data: sampleData },
    });
    // tbody rows: 2 workcenters + 1 total row = 3
    const rows = wrapper.findAll('tbody tr');
    expect(rows.length).toBe(3);
  });

  it('emits select with normalized filter when a cell is clicked', async () => {
    const wrapper = mount(HoldMatrix, {
      props: { data: sampleData },
    });
    // Find first data cell in tbody (skip row-name td)
    const tbody = wrapper.find('tbody');
    const firstRow = tbody.findAll('tr')[0];
    const cells = firstRow.findAll('td.clickable');
    // cells[0] is the row-name (workcenter), cells[1] is first package cell
    await cells[1].trigger('click');
    expect(wrapper.emitted('select')).toBeTruthy();
    const emittedPayload = wrapper.emitted('select')[0][0];
    expect(emittedPayload).not.toBeNull();
    expect(emittedPayload.workcenter).toBe('WC-A');
    expect(emittedPayload.package).toBe('PKG1');
  });

  it('emits select with workcenter only when row-name is clicked', async () => {
    const wrapper = mount(HoldMatrix, {
      props: { data: sampleData },
    });
    const rowName = wrapper.find('td.row-name');
    await rowName.trigger('click');
    expect(wrapper.emitted('select')).toBeTruthy();
    const payload = wrapper.emitted('select')[0][0];
    expect(payload.workcenter).toBe('WC-A');
    expect(payload.package).toBeNull();
  });

  it('emits select null (toggle off) when same filter is clicked again', async () => {
    const wrapper = mount(HoldMatrix, {
      props: {
        data: sampleData,
        activeFilter: { workcenter: 'WC-A', package: 'PKG1' },
      },
    });
    const tbody = wrapper.find('tbody');
    const firstRow = tbody.findAll('tr')[0];
    const cells = firstRow.findAll('td.clickable');
    await cells[1].trigger('click');
    const payload = wrapper.emitted('select')[0][0];
    // Same filter => toggles off to null
    expect(payload).toBeNull();
  });

  it('renders without crash when matrix values are missing for a cell', () => {
    const sparseData = {
      workcenters: ['WC-X'],
      packages: ['PKG-MISSING'],
      matrix: {}, // no data at all
      workcenter_totals: {},
      package_totals: {},
      grand_total: 0,
    };
    const wrapper = mount(HoldMatrix, {
      props: { data: sparseData },
    });
    expect(wrapper.exists()).toBe(true);
    // Cell should show '-' or '0'
    const tbody = wrapper.find('tbody');
    expect(tbody.exists()).toBe(true);
  });
});
