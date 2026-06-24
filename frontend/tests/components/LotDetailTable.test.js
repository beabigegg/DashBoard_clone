// @vitest-environment jsdom
/**
 * LotTable component tests (wip-detail variant)
 *
 * Focuses on:
 *   - Type column visible (from lot.pjType), positioned immediately right of LOT ID
 *   - Type column is sortable
 *   - null/undefined pjType renders as '-'
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import LotTable from '../../src/wip-detail/components/LotTable.vue';

const makeLot = (overrides = {}) => ({
  lotId: 'LOT001',
  pjType: 'STANDARD',
  equipment: 'EQ-A',
  wipStatus: 'QUEUE',
  holdReason: null,
  package: 'PKG1',
  spec: 'S1',
  qty: 100,
  ...overrides,
});

const sampleData = {
  lots: [
    makeLot({ lotId: 'LOT001', pjType: 'STANDARD' }),
    makeLot({ lotId: 'LOT002', pjType: 'PROTO', equipment: 'EQ-B' }),
    makeLot({ lotId: 'LOT003', pjType: null }),
  ],
  specs: ['S1'],
  pagination: { page: 1, page_size: 20, total_count: 3, total_pages: 1 },
};

describe('LotTable - Type column', () => {
  it('renders Type column header immediately after LOT ID', () => {
    const wrapper = mount(LotTable, {
      props: { data: sampleData },
    });
    const headers = wrapper.findAll('thead th').map((th) => th.text().replace(/[▲▼⇕]/g, '').trim());
    const lotIdIdx = headers.findIndex((h) => h === 'LOT ID');
    const typeIdx = headers.findIndex((h) => h === 'Type');
    expect(lotIdIdx).toBeGreaterThanOrEqual(0);
    expect(typeIdx).toBe(lotIdIdx + 1);
  });

  it('renders pjType value in Type column cells', () => {
    const wrapper = mount(LotTable, {
      props: { data: sampleData },
    });
    const rows = wrapper.findAll('tbody tr');
    // First row: LOT ID cell (button), then Type cell
    const firstRow = rows[0];
    const cells = firstRow.findAll('td.fixed-col');
    // cells[0] = LOT ID (button inside), cells[1] = Type
    expect(cells[1].text()).toBe('STANDARD');
  });

  it('renders "-" when pjType is null', () => {
    const wrapper = mount(LotTable, {
      props: { data: sampleData },
    });
    const rows = wrapper.findAll('tbody tr');
    const thirdRow = rows[2];
    const cells = thirdRow.findAll('td.fixed-col');
    expect(cells[1].text()).toBe('-');
  });

  it('renders "-" when pjType is undefined', () => {
    const dataWithUndefined = {
      ...sampleData,
      lots: [makeLot({ pjType: undefined })],
    };
    const wrapper = mount(LotTable, {
      props: { data: dataWithUndefined },
    });
    const rows = wrapper.findAll('tbody tr');
    const cells = rows[0].findAll('td.fixed-col');
    expect(cells[1].text()).toBe('-');
  });

  it('Type column header has sort indicator and is clickable', async () => {
    const wrapper = mount(LotTable, {
      props: { data: sampleData },
    });
    const headers = wrapper.findAll('thead th');
    const typeHeader = headers.find((th) => th.text().replace(/[▲▼⇕]/g, '').trim() === 'Type');
    expect(typeHeader).toBeTruthy();
    expect(typeHeader.classes()).toContain('sortable-th');
    // Click to sort ascending
    await typeHeader.trigger('click');
    expect(typeHeader.attributes('aria-sort')).toBe('ascending');
    // Click again to sort descending
    await typeHeader.trigger('click');
    expect(typeHeader.attributes('aria-sort')).toBe('descending');
  });

  it('sorting by pjType orders rows correctly', async () => {
    const data = {
      lots: [
        makeLot({ lotId: 'LOT-Z', pjType: 'ZZTYPE' }),
        makeLot({ lotId: 'LOT-A', pjType: 'AATYPE' }),
        makeLot({ lotId: 'LOT-M', pjType: 'MMTYPE' }),
      ],
      specs: [],
      pagination: { page: 1, page_size: 20, total_count: 3, total_pages: 1 },
    };
    const wrapper = mount(LotTable, {
      props: { data },
    });
    const headers = wrapper.findAll('thead th');
    const typeHeader = headers.find((th) => th.text().replace(/[▲▼⇕]/g, '').trim() === 'Type');
    // Sort ascending
    await typeHeader.trigger('click');
    const rows = wrapper.findAll('tbody tr');
    const typeCells = rows.map((row) => row.findAll('td.fixed-col')[1].text());
    expect(typeCells).toEqual(['AATYPE', 'MMTYPE', 'ZZTYPE']);
  });

  it('renders table without crash when all lots have pjType null', () => {
    const data = {
      lots: [
        makeLot({ pjType: null }),
        makeLot({ pjType: null }),
      ],
      specs: [],
      pagination: { page: 1, page_size: 20, total_count: 2, total_pages: 1 },
    };
    const wrapper = mount(LotTable, {
      props: { data },
    });
    expect(wrapper.exists()).toBe(true);
    const rows = wrapper.findAll('tbody tr');
    rows.forEach((row) => {
      const cells = row.findAll('td.fixed-col');
      expect(cells[1].text()).toBe('-');
    });
  });
});
