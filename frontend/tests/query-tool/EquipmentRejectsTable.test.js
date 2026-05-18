// @vitest-environment jsdom
/**
 * Vitest component test for EquipmentRejectsTable.vue
 *
 * Acceptance criteria AC-6:
 * 1. Renders empty state without crash when rows is empty
 * 2. Renders detail row columns (CONTAINERNAME, LOSSREASONNAME) when data provided
 * 3. Old aggregate column headers (TOTAL_REJECT_QTY, TOTAL_DEFECT_QTY, AFFECTED_LOT_COUNT)
 *    are NOT present in the rendered output
 *
 * equipment-rejects-by-lots AC-6
 */

import { describe, expect, it, vi } from 'vitest';
import { shallowMount } from '@vue/test-utils';

// useSortableTable: return source data as-is (no interactive sort needed in unit tests)
vi.mock('../../src/shared-composables/useSortableTable', () => {
  const { ref, computed } = require('vue');
  return {
    useSortableTable: (source) => {
      const sortKey = ref('');
      const sortDirection = ref('asc');
      const sortedData = computed(() => source.value);
      function toggleSort(key) {
        if (sortKey.value === key) {
          sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
        } else {
          sortKey.value = key;
          sortDirection.value = 'asc';
        }
      }
      return { sortKey, sortDirection, sortedData, toggleSort };
    },
  };
});

import EquipmentRejectsTable from '../../src/query-tool/components/EquipmentRejectsTable.vue';

describe('EquipmentRejectsTable', () => {
  it('renders empty state without crash when rows is empty', () => {
    const wrapper = shallowMount(EquipmentRejectsTable, {
      props: { rows: [], loading: false },
    });
    // Should show empty placeholder text
    const text = wrapper.text();
    expect(text).toContain('無報廢資料');
    // No table element when there are no rows
    expect(wrapper.find('table').exists()).toBe(false);
  });

  it('renders CONTAINERNAME and LOSSREASONNAME cells when data is provided', () => {
    const sampleRow = {
      CONTAINERNAME: 'LOT-001',
      WORKCENTERNAME: 'STA-A',
      SPECNAME: 'SPEC-X',
      LOSSREASONNAME: '碎片',
      REJECT_TOTAL_QTY: 5,
      DEFECT_QTY: 2,
      REJECTCOMMENT: '測試',
      EQUIPMENTNAME: 'FURNACE-B',
      TXN_TIME: '2026-05-18 10:00:00',
    };

    const wrapper = shallowMount(EquipmentRejectsTable, {
      props: { rows: [sampleRow], loading: false },
    });

    const html = wrapper.html();
    // CONTAINERNAME cell should be present
    expect(html).toContain('LOT-001');
    // LOSSREASONNAME cell should be present
    expect(html).toContain('碎片');
    // EQUIPMENTNAME cell (報廢登錄設備) should be present
    expect(html).toContain('FURNACE-B');
    // Table should render
    expect(wrapper.find('table').exists()).toBe(true);
  });

  it('does NOT render old aggregate column headers', () => {
    const sampleRow = {
      CONTAINERNAME: 'LOT-002',
      LOSSREASONNAME: '污染',
      REJECT_TOTAL_QTY: 3,
    };

    const wrapper = shallowMount(EquipmentRejectsTable, {
      props: { rows: [sampleRow], loading: false },
    });

    const html = wrapper.html();
    // Old aggregate column names must not appear
    expect(html).not.toContain('TOTAL_REJECT_QTY');
    expect(html).not.toContain('TOTAL_DEFECT_QTY');
    expect(html).not.toContain('AFFECTED_LOT_COUNT');
  });

  it('shows loading state via BlockLoadingState stub when loading=true', () => {
    const wrapper = shallowMount(EquipmentRejectsTable, {
      props: { rows: [], loading: true },
    });
    // With shallowMount, BlockLoadingState is rendered as <block-loading-state-stub>
    expect(wrapper.find('block-loading-state-stub').exists()).toBe(true);
  });

  it('shows row-limit banner when truncated=true', () => {
    const wrapper = shallowMount(EquipmentRejectsTable, {
      props: { rows: [], loading: false, truncated: true },
    });
    const text = wrapper.text();
    expect(text).toContain('資料已截斷');
  });

  it('shows cross-station parenthetical in EQUIPMENTNAME column header', () => {
    const sampleRow = {
      CONTAINERNAME: 'LOT-003',
      EQUIPMENTNAME: 'EQP-C',
    };

    const wrapper = shallowMount(EquipmentRejectsTable, {
      props: { rows: [sampleRow], loading: false },
    });

    const html = wrapper.html();
    // Column header should clarify it may differ from queried equipment
    expect(html).toContain('報廢登錄設備');
    expect(html).toContain('可能不同於查詢設備');
  });
});
