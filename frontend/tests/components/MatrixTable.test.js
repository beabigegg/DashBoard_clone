// @vitest-environment jsdom
/**
 * MatrixTable component tests (wip-overview variant)
 *
 * Props:
 *   data: Object — { workcenters, packages, matrix, workcenter_totals, package_totals, grand_total }
 *   activeFilter: Object — { workcenter?, package? }
 *
 * Emits: 'drilldown' — payload is { workcenter, package } for cell click,
 *                       { workcenter, package: null } for row header click,
 *                       null for toggle-off.
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import MatrixTable from '../../src/wip-overview/components/MatrixTable.vue';

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

describe('MatrixTable', () => {
  it('renders table when data has workcenters', () => {
    const wrapper = mount(MatrixTable, {
      props: { data: sampleData },
    });
    expect(wrapper.find('table.matrix-table').exists()).toBe(true);
  });

  it('renders placeholder when workcenters is empty', () => {
    const wrapper = mount(MatrixTable, {
      props: { data: { workcenters: [], packages: [], matrix: {} } },
    });
    expect(wrapper.find('.placeholder').exists()).toBe(true);
    expect(wrapper.find('table').exists()).toBe(false);
  });

  it('renders placeholder when data is null', () => {
    const wrapper = mount(MatrixTable, {
      props: { data: null },
    });
    expect(wrapper.find('.placeholder').exists()).toBe(true);
  });

  it('renders correct number of workcenter rows', () => {
    const wrapper = mount(MatrixTable, {
      props: { data: sampleData },
    });
    // tbody rows: 2 workcenters + 1 total row = 3
    const rows = wrapper.findAll('tbody tr');
    expect(rows.length).toBe(3);
  });

  it('emits drilldown with { workcenter, package } on cell click', async () => {
    const wrapper = mount(MatrixTable, {
      props: { data: sampleData },
    });
    const tbody = wrapper.find('tbody');
    const firstRow = tbody.findAll('tr')[0];
    // cells: [row-name (clickable), pkg1 cell (clickable), pkg2 cell (clickable), total (clickable)]
    const cells = firstRow.findAll('td.clickable');
    // cells[0] is the row-name td, cells[1] is the first package cell
    await cells[1].trigger('click');
    expect(wrapper.emitted('drilldown')).toBeTruthy();
    const payload = wrapper.emitted('drilldown')[0][0];
    expect(payload).not.toBeNull();
    expect(payload.workcenter).toBe('WC-A');
    expect(payload.package).toBe('PKG1');
  });

  it('emits drilldown with { workcenter, package: null } on row header click', async () => {
    const wrapper = mount(MatrixTable, {
      props: { data: sampleData },
    });
    const rowName = wrapper.find('td.row-name');
    await rowName.trigger('click');
    expect(wrapper.emitted('drilldown')).toBeTruthy();
    const payload = wrapper.emitted('drilldown')[0][0];
    expect(payload.workcenter).toBe('WC-A');
    expect(payload.package).toBeNull();
  });

  it('emits drilldown null (toggle off) when same cell filter is clicked again', async () => {
    const wrapper = mount(MatrixTable, {
      props: {
        data: sampleData,
        activeFilter: { workcenter: 'WC-A', package: 'PKG1' },
      },
    });
    const tbody = wrapper.find('tbody');
    const firstRow = tbody.findAll('tr')[0];
    const cells = firstRow.findAll('td.clickable');
    await cells[1].trigger('click');
    const payload = wrapper.emitted('drilldown')[0][0];
    // Same cell filter => toggles off to null
    expect(payload).toBeNull();
  });

  it('emits drilldown null (toggle off) when same row filter is clicked again', async () => {
    const wrapper = mount(MatrixTable, {
      props: {
        data: sampleData,
        activeFilter: { workcenter: 'WC-A', package: null },
      },
    });
    const rowName = wrapper.find('td.row-name');
    await rowName.trigger('click');
    const payload = wrapper.emitted('drilldown')[0][0];
    expect(payload).toBeNull();
  });

  it('applies active class to row-name when row is active filter', () => {
    const wrapper = mount(MatrixTable, {
      props: {
        data: sampleData,
        activeFilter: { workcenter: 'WC-A', package: null },
      },
    });
    const rowName = wrapper.find('td.row-name');
    expect(rowName.classes()).toContain('active');
  });

  it('applies active class to cell when cell is active filter', () => {
    const wrapper = mount(MatrixTable, {
      props: {
        data: sampleData,
        activeFilter: { workcenter: 'WC-A', package: 'PKG1' },
      },
    });
    const tbody = wrapper.find('tbody');
    const firstRow = tbody.findAll('tr')[0];
    const cells = firstRow.findAll('td.clickable');
    // cells[1] is the PKG1 data cell for WC-A
    expect(cells[1].classes()).toContain('active');
  });

  it('does not apply active class to cell when different filter is active', () => {
    const wrapper = mount(MatrixTable, {
      props: {
        data: sampleData,
        activeFilter: { workcenter: 'WC-B', package: 'PKG2' },
      },
    });
    const tbody = wrapper.find('tbody');
    const firstRow = tbody.findAll('tr')[0];
    const cells = firstRow.findAll('td.clickable');
    // cells[1] is PKG1 for WC-A — should not be active
    expect(cells[1].classes()).not.toContain('active');
  });

  it('renders without crash when matrix values are missing for a cell', () => {
    const sparseData = {
      workcenters: ['WC-X'],
      packages: ['PKG-MISSING'],
      matrix: {},
      workcenter_totals: {},
      package_totals: {},
      grand_total: 0,
    };
    const wrapper = mount(MatrixTable, {
      props: { data: sparseData },
    });
    expect(wrapper.exists()).toBe(true);
    expect(wrapper.find('tbody').exists()).toBe(true);
  });
});
