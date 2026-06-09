// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { ref } from 'vue';

import { useCrossFilter } from '../../src/resource-status/composables/useCrossFilter';

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeEq(overrides: Record<string, unknown> = {}) {
  return {
    RESOURCEID: 'R001',
    RESOURCENAME: 'Machine-A',
    EQUIPMENTASSETSSTATUS: 'PRD',
    WORKCENTER_GROUP: 'G1',
    WORKCENTER_GROUP_SEQ: 1,
    RESOURCEFAMILYNAME: 'FAMILY_A',
    WORKCENTERNAME: 'WC1',
    LOCATIONNAME: 'LOC1',
    LOT_COUNT: 0,
    LOT_DETAILS: [],
    JOBORDER: '',
    JOBSTATUS: '',
    JOBMODEL: '',
    JOBSTAGE: '',
    JOBID: '',
    CREATEDATE: '',
    CREATEUSERNAME: '',
    CREATEUSER: '',
    TECHNICIANUSERNAME: '',
    TECHNICIANUSER: '',
    SYMPTOMCODE: '',
    CAUSECODE: '',
    REPAIRCODE: '',
    STATUS_CATEGORY: 'prd',
    PACKAGEGROUPNAME: 'QFP',
    ...overrides,
  };
}

const FIXTURE_EQUIPMENT = [
  makeEq({ RESOURCEID: 'R001', WORKCENTER_GROUP: 'G1', EQUIPMENTASSETSSTATUS: 'PRD', PACKAGEGROUPNAME: 'QFP' }),
  makeEq({ RESOURCEID: 'R002', WORKCENTER_GROUP: 'G1', EQUIPMENTASSETSSTATUS: 'UDT', STATUS_CATEGORY: 'udt', PACKAGEGROUPNAME: 'QFP' }),
  makeEq({ RESOURCEID: 'R003', WORKCENTER_GROUP: 'G2', EQUIPMENTASSETSSTATUS: 'PRD', PACKAGEGROUPNAME: 'BGA' }),
  makeEq({ RESOURCEID: 'R004', WORKCENTER_GROUP: 'G2', EQUIPMENTASSETSSTATUS: 'UDT', STATUS_CATEGORY: 'udt', PACKAGEGROUPNAME: 'BGA' }),
  makeEq({ RESOURCEID: 'R005', WORKCENTER_GROUP: 'G1', EQUIPMENTASSETSSTATUS: 'PRD', PACKAGEGROUPNAME: null }),
];

describe('useCrossFilter — composable', () => {
  it('initial_state_is_empty — activeSelections is []; filteredEquipment equals allEquipment', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { activeSelections, filteredEquipment } = useCrossFilter(equipment);

    expect(activeSelections.value).toHaveLength(0);
    expect(filteredEquipment.value).toEqual(FIXTURE_EQUIPMENT);
  });

  it('select_ring_filters_by_workcenter_group_and_status — narrows to G1+PRD rows only', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    addSelection({
      source: 'ring',
      label: 'G1 / PRD',
      predicate: (row) => row.WORKCENTER_GROUP === 'G1' && row.EQUIPMENTASSETSSTATUS === 'PRD',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    expect(ids).toContain('R001');
    expect(ids).not.toContain('R002');
    expect(ids).not.toContain('R003');
    expect(ids).not.toContain('R004');
    // R005 is G1+PRD (null package)
    expect(ids).toContain('R005');
  });

  it('and_intersection_two_active_selections — ring=G1 AND heatmap=QFP returns rows satisfying both', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    addSelection({
      source: 'ring',
      label: 'G1',
      predicate: (row) => row.WORKCENTER_GROUP === 'G1',
    });
    addSelection({
      source: 'heatmap',
      label: 'QFP',
      predicate: (row) => (row.PACKAGEGROUPNAME?.trim() || '—') === 'QFP',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    // G1 + QFP: R001, R002
    expect(ids).toContain('R001');
    expect(ids).toContain('R002');
    expect(ids).not.toContain('R003');
    expect(ids).not.toContain('R004');
    expect(ids).not.toContain('R005');
  });

  it('and_intersection_three_active_selections — three simultaneous predicates all must hold', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    addSelection({
      source: 'ring',
      label: 'G1',
      predicate: (row) => row.WORKCENTER_GROUP === 'G1',
    });
    addSelection({
      source: 'heatmap',
      label: 'QFP',
      predicate: (row) => (row.PACKAGEGROUPNAME?.trim() || '—') === 'QFP',
    });
    addSelection({
      source: 'matrix',
      label: 'PRD',
      predicate: (row) => row.EQUIPMENTASSETSSTATUS === 'PRD',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    // G1 + QFP + PRD: R001 only
    expect(ids).toEqual(['R001']);
  });

  it('reclick_same_key_removes_selection — second add on same source removes entry; subset restored', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment, activeSelections } = useCrossFilter(equipment);

    const sel = {
      source: 'ring' as const,
      label: 'G1',
      predicate: (row: (typeof FIXTURE_EQUIPMENT)[0]) => row.WORKCENTER_GROUP === 'G1',
    };

    addSelection(sel);
    expect(activeSelections.value).toHaveLength(1);

    // Adding again same source toggles it off
    addSelection(sel);
    expect(activeSelections.value).toHaveLength(0);
    expect(filteredEquipment.value).toEqual(FIXTURE_EQUIPMENT);
  });

  it('clear_all_removes_every_selection — clearAll() resets filteredEquipment to allEquipment', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, clearAll, filteredEquipment, activeSelections } = useCrossFilter(equipment);

    addSelection({ source: 'ring', label: 'G1', predicate: (row) => row.WORKCENTER_GROUP === 'G1' });
    addSelection({ source: 'heatmap', label: 'QFP', predicate: (row) => (row.PACKAGEGROUPNAME?.trim() || '—') === 'QFP' });
    expect(activeSelections.value).toHaveLength(2);

    clearAll();
    expect(activeSelections.value).toHaveLength(0);
    expect(filteredEquipment.value).toEqual(FIXTURE_EQUIPMENT);
  });

  it('exclude_self_ring_dimension_unaffected_by_ring_selection — ring chart input set omits ring own predicate', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, getInputForChart } = useCrossFilter(equipment);

    addSelection({
      source: 'ring',
      label: 'G1',
      predicate: (row) => row.WORKCENTER_GROUP === 'G1',
    });

    // Ring's own input set (exclude-self) should still contain all equipment
    const ringInput = getInputForChart('ring');
    expect(ringInput.value).toEqual(FIXTURE_EQUIPMENT);
  });

  it('exclude_self_heatmap_dimension_unaffected_by_heatmap_selection — heatmap package list unaffected by heatmap selection', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, getInputForChart } = useCrossFilter(equipment);

    // Add ring selection (narrows to G1) AND heatmap selection (narrows to QFP)
    addSelection({
      source: 'ring',
      label: 'G1',
      predicate: (row) => row.WORKCENTER_GROUP === 'G1',
    });
    addSelection({
      source: 'heatmap',
      label: 'QFP',
      predicate: (row) => (row.PACKAGEGROUPNAME?.trim() || '—') === 'QFP',
    });

    // Heatmap's input set excludes heatmap's own selection but applies ring selection
    const heatmapInput = getInputForChart('heatmap');
    const ids = heatmapInput.value.map((e) => e.RESOURCEID);
    // Only ring filter applies: G1 rows = R001, R002, R005
    expect(ids).toContain('R001');
    expect(ids).toContain('R002');
    expect(ids).toContain('R005');
    // G2 rows excluded by ring
    expect(ids).not.toContain('R003');
    expect(ids).not.toContain('R004');
  });

  it('heatmap_null_packagegroupname_normalises_to_dash — null/empty PACKAGEGROUPNAME treated as "—" in predicate', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    // R005 has PACKAGEGROUPNAME: null — should be normalised to '—'
    addSelection({
      source: 'heatmap',
      label: '—',
      predicate: (row) => (row.PACKAGEGROUPNAME?.trim() || '—') === '—',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    expect(ids).toContain('R005');
    expect(ids).not.toContain('R001');
    expect(ids).not.toContain('R002');
    expect(ids).not.toContain('R003');
    expect(ids).not.toContain('R004');
  });

  it('matrix_dimension_via_composable — matrix cell-filter produces same narrowing as old matrixFilter[] toggle', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    // Matrix filter: G2, status PRD
    addSelection({
      source: 'matrix',
      label: 'G2 / PRD',
      predicate: (row) => row.WORKCENTER_GROUP === 'G2' && row.EQUIPMENTASSETSSTATUS === 'PRD',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    expect(ids).toContain('R003');
    expect(ids).not.toContain('R001');
    expect(ids).not.toContain('R002');
    expect(ids).not.toContain('R004');
    expect(ids).not.toContain('R005');
  });

  it('summary_card_status_dimension_via_composable — summary-card status routes to status predicate in composable', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    addSelection({
      source: 'summary',
      label: 'UDT',
      predicate: (row) => row.EQUIPMENTASSETSSTATUS === 'UDT',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    expect(ids).toContain('R002');
    expect(ids).toContain('R004');
    expect(ids).not.toContain('R001');
    expect(ids).not.toContain('R003');
    expect(ids).not.toContain('R005');
  });

  it('alerts_resourceid_dimension_filters_to_single_resource — Alerts row click; filteredEquipment contains only that RESOURCEID', () => {
    const equipment = ref(FIXTURE_EQUIPMENT);
    const { addSelection, filteredEquipment } = useCrossFilter(equipment);

    addSelection({
      source: 'alerts',
      label: 'R003',
      predicate: (row) => row.RESOURCEID === 'R003',
    });

    const ids = filteredEquipment.value.map((e) => e.RESOURCEID);
    expect(ids).toEqual(['R003']);
  });
});
