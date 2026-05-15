// @vitest-environment jsdom
/**
 * ProductionDetailTable component tests — AC-6 (partial_count badge)
 *
 * Verifies that a merge-count badge (×N 合併) appears next to the lot_id
 * cell value when partial_count > 1 and is absent otherwise.
 *
 * Test names match test-plan.md AC-6 frontend row exactly.
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import ProductionDetailTable from '../../src/production-history/components/ProductionDetailTable.vue';

/** Minimal DetailRow fixture */
function makeRow(overrides = {}) {
  return {
    lot_id: 'LOT-001',
    pj_type: 'STANDARD',
    bop: 'BOP-A',
    pj_function: 'FN-1',
    work_order: 'WO-001',
    wafer_lot: null,
    package_name: 'PKG1',
    workcenter: 'WC-A',
    spec: 'SPEC-01',
    equipment_id: 'EQ-001',
    equipment_name: 'EQ-NAME-A',
    trackin_time: '2026-05-15T08:00:00',
    trackout_time: '2026-05-15T10:00:00',
    trackin_qty: 25,
    trackout_qty: 25,
    ...overrides,
  };
}

const defaultPagination = { page: 1, per_page: 25, total_rows: 1, total_pages: 1 };

describe('ProductionDetailTable - partial_count badge (AC-6)', () => {
  it('test partial_count badge renders when value gt 1', async () => {
    const row = makeRow({ partial_count: 3 });
    const wrapper = mount(ProductionDetailTable, {
      props: { rows: [row], pagination: defaultPagination },
    });
    // DataTableColumn registers columns in onMounted; flush reactivity before asserting.
    await nextTick();
    // Badge text must contain ×3 合併
    expect(wrapper.text()).toContain('×3 合併');
  });

  it('test partial_count badge absent when value equals 1', async () => {
    const row = makeRow({ partial_count: 1 });
    const wrapper = mount(ProductionDetailTable, {
      props: { rows: [row], pagination: defaultPagination },
    });
    await nextTick();
    // No badge text when partial_count is exactly 1
    expect(wrapper.text()).not.toContain('合併');
  });

  it('test partial_count badge absent when value is undefined (defensive rollback coverage)', async () => {
    const row = makeRow(); // no partial_count field
    const wrapper = mount(ProductionDetailTable, {
      props: { rows: [row], pagination: defaultPagination },
    });
    await nextTick();
    expect(wrapper.text()).not.toContain('合併');
  });
});
