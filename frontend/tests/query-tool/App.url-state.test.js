// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick, ref } from 'vue';
import { shallowMount } from '@vue/test-utils';

let lotResolveState;
let reverseResolveState;
let lotLineageState;
let reverseLineageState;
let lotDetailState;
let reverseDetailState;
let equipmentQueryState;
let lotEquipmentQueryState;

const useLotResolveMock = vi.fn();
const useLotDetailMock = vi.fn();
const useEquipmentQueryMock = vi.fn();
const useLotEquipmentQueryMock = vi.fn();
const replaceRuntimeHistoryMock = vi.fn();

function makeLotResolveState() {
  return {
    inputType: ref('lot_id'),
    inputText: ref(''),
    inputTypeOptions: ['lot_id', 'work_order', 'serial_number', 'gd_lot_id'],
    inputLimit: ref(50),
    loading: { resolving: false },
    resolvedLots: ref([]),
    notFound: ref([]),
    errorMessage: ref(''),
    successMessage: ref(''),
    setInputType(value) {
      this.inputType.value = value;
    },
    setInputText(value) {
      this.inputText.value = value;
    },
    resolveLots: vi.fn(async () => ({ ok: true })),
  };
}

function makeDetailState() {
  return {
    selectedContainerId: ref(''),
    selectedContainerIds: ref([]),
    activeSubTab: ref('history'),
    workcenterGroups: ref([]),
    selectedWorkcenterGroups: ref([]),
    historyRows: ref([]),
    associationRows: { materials: [], rejects: [], holds: [], jobs: [] },
    pagination: {
      history: { page: 1, per_page: 25, total: 0, total_pages: 1 },
      materials: { page: 1, per_page: 25, total: 0, total_pages: 1 },
      rejects: { page: 1, per_page: 25, total: 0, total_pages: 1 },
      holds: { page: 1, per_page: 25, total: 0, total_pages: 1 },
      jobs: { page: 1, per_page: 0, total: 0, total_pages: 1 },
    },
    qualityMeta: {
      history: null,
      materials: null,
      rejects: null,
      holds: null,
      jobs: null,
    },
    loading: {
      workcenterGroups: false,
      history: false,
      materials: false,
      rejects: false,
      holds: false,
      jobs: false,
    },
    loaded: {
      history: false,
      materials: false,
      rejects: false,
      holds: false,
      jobs: false,
    },
    errors: {
      history: '',
      materials: '',
      rejects: '',
      holds: '',
      jobs: '',
      workcenterGroups: '',
    },
    exporting: {
      history: false,
      materials: false,
      rejects: false,
      holds: false,
      jobs: false,
    },
    pageSizeOptions: [25, 50, 100, 200],
    loadWorkcenterGroups: vi.fn(async () => true),
    setSelectedContainerId: vi.fn(async function setSelectedContainerId(value) {
      this.selectedContainerId.value = value;
      this.selectedContainerIds.value = value ? [value] : [];
      return true;
    }),
    setSelectedContainerIds: vi.fn(async function setSelectedContainerIds(values) {
      this.selectedContainerIds.value = values;
      this.selectedContainerId.value = values[0] || '';
      return true;
    }),
    setActiveSubTab: vi.fn(async function setActiveSubTab(value) {
      this.activeSubTab.value = value;
      return true;
    }),
    setSelectedWorkcenterGroups: vi.fn(async function setSelectedWorkcenterGroups(values) {
      this.selectedWorkcenterGroups.value = values;
      return true;
    }),
    setSubTabPage: vi.fn(async () => true),
    setSubTabPerPage: vi.fn(async () => true),
    exportSubTab: vi.fn(async () => true),
    clearTabData: vi.fn(),
  };
}

function makeEquipmentQueryState() {
  return {
    selectedEquipmentIds: ref([]),
    startDate: ref(''),
    endDate: ref(''),
    activeSubTab: ref('lots'),
    equipmentOptionItems: ref([]),
    lotsRows: ref([]),
    jobsRows: ref([]),
    rejectsRows: ref([]),
    statusRows: ref([]),
    lotsPagination: ref({ page: 1, per_page: 25, total: 0, total_pages: 1 }),
    loading: { lots: false, jobs: false, rejects: false, statusHours: false, bootstrap: false },
    errors: { filters: '', lots: '', jobs: '', rejects: '', statusHours: '' },
    exporting: { lots: false, jobs: false, rejects: false },
    canExportSubTab: () => false,
    pageSizeOptions: [25, 50, 100, 200],
    queried: { timeline: false },
    bootstrap: vi.fn(async () => true),
    setSelectedEquipmentIds: vi.fn(function setSelectedEquipmentIds(values) {
      this.selectedEquipmentIds.value = values;
    }),
    resetDateRange: vi.fn(),
    setActiveSubTab: vi.fn(async function setActiveSubTab(value) {
      this.activeSubTab.value = value;
      return true;
    }),
    queryActiveSubTab: vi.fn(async () => true),
    exportSubTab: vi.fn(async () => true),
    queryLots: vi.fn(async () => true),
  };
}

function makeLotEquipmentQueryState() {
  return {
    inputType: ref('lot_id'),
    inputTypeOptions: ['lot_id'],
    inputText: ref(''),
    parsedInputCount: ref(0),
    workcenterGroupOptions: ref([]),
    selectedWorkcenterGroups: ref([]),
    resolvedEquipmentIds: ref([]),
    resolvedEquipmentNames: ref([]),
    lookupMessage: ref(''),
    traceEntries: ref([]),
    startDate: ref(''),
    endDate: ref(''),
    activeSubTab: ref('lots'),
    lotsRows: ref([]),
    jobsRows: ref([]),
    rejectsRows: ref([]),
    lotsPagination: ref({ page: 1, per_page: 25, total: 0, total_pages: 1 }),
    loading: { lookup: false, lots: false, jobs: false, rejects: false, bootstrap: false },
    errors: { input: '', lookup: '', lots: '', jobs: '', rejects: '' },
    exporting: { lots: false, jobs: false, rejects: false },
    canExportSubTab: () => false,
    pageSizeOptions: [25, 50, 100, 200],
    bootstrap: vi.fn(async () => true),
    lookupEquipment: vi.fn(async () => true),
    setActiveSubTab: vi.fn(async function setActiveSubTab(value) {
      this.activeSubTab.value = value;
      return true;
    }),
    exportSubTab: vi.fn(async () => true),
    changeLotsPage: vi.fn(),
    changeLotsPerPage: vi.fn(),
  };
}

function makeLineageState() {
  return {
    selectedContainerId: ref(''),
    selectedContainerIds: ref([]),
    treeRoots: ref([]),
    lineageMap: new Map(),
    nameMap: new Map(),
    nodeMetaMap: new Map(),
    edgeTypeMap: new Map(),
    graphEdges: ref([]),
    leafSerials: new Map(),
    lineageLoading: ref(false),
    selectNode: vi.fn(function selectNode(value) {
      this.selectedContainerId.value = value;
    }),
    primeResolvedLots: vi.fn(async () => true),
    clearSelection: vi.fn(),
    setSelectedNodes: vi.fn(),
    getSubtreeCids: vi.fn((value) => [value]),
  };
}

vi.mock('../../src/core/shell-navigation.js', () => ({
  replaceRuntimeHistory: replaceRuntimeHistoryMock,
}));

vi.mock('../../src/shared-composables/useRequestGuard.js', () => ({
  useRequestGuard: () => ({ nextRequestId: vi.fn() }),
}));

vi.mock('../../src/query-tool/composables/useLotResolve.js', () => ({
  useLotResolve: useLotResolveMock,
}));

vi.mock('../../src/query-tool/composables/useLotDetail.js', () => ({
  useLotDetail: useLotDetailMock,
}));

vi.mock('../../src/query-tool/composables/useLotLineage.js', () => ({
  useLotLineage: () => lotLineageState,
}));

vi.mock('../../src/query-tool/composables/useReverseLineage.js', () => ({
  useReverseLineage: () => reverseLineageState,
}));

vi.mock('../../src/query-tool/composables/useEquipmentQuery.js', () => ({
  useEquipmentQuery: useEquipmentQueryMock,
}));

vi.mock('../../src/query-tool/composables/useLotEquipmentQuery.js', () => ({
  useLotEquipmentQuery: useLotEquipmentQueryMock,
}));

describe('Query Tool App URL state', () => {
  beforeEach(() => {
    vi.resetModules();
    useLotResolveMock.mockReset();
    useLotDetailMock.mockReset();
    useEquipmentQueryMock.mockReset();
    useLotEquipmentQueryMock.mockReset();
    replaceRuntimeHistoryMock.mockReset();

    lotResolveState = makeLotResolveState();
    reverseResolveState = makeLotResolveState();
    lotLineageState = makeLineageState();
    reverseLineageState = makeLineageState();
    lotDetailState = makeDetailState();
    reverseDetailState = makeDetailState();
    equipmentQueryState = makeEquipmentQueryState();
    lotEquipmentQueryState = makeLotEquipmentQueryState();

    useLotResolveMock
      .mockReturnValueOnce(lotResolveState)
      .mockReturnValueOnce(reverseResolveState);

    useLotDetailMock
      .mockReturnValueOnce(lotDetailState)
      .mockReturnValueOnce(reverseDetailState);

    useEquipmentQueryMock.mockImplementation((options = {}) => {
      equipmentQueryState.selectedEquipmentIds.value = options.selectedEquipmentIds || [];
      equipmentQueryState.startDate.value = options.startDate || '';
      equipmentQueryState.endDate.value = options.endDate || '';
      equipmentQueryState.activeSubTab.value = options.activeSubTab || 'lots';
      return equipmentQueryState;
    });

    useLotEquipmentQueryMock.mockImplementation((options = {}) => {
      lotEquipmentQueryState.inputType.value = options.inputType || 'lot_id';
      lotEquipmentQueryState.inputText.value = options.inputText || '';
      lotEquipmentQueryState.selectedWorkcenterGroups.value = options.workcenterGroups || [];
      lotEquipmentQueryState.activeSubTab.value = options.activeSubTab || 'lots';
      return lotEquipmentQueryState;
    });
  });

  it('restores reverse deep-link state from URL on mount', async () => {
    window.history.replaceState({}, '', '/query-tool?tab=reverse&reverse_input_type=gd_lot_id&reverse_values=GD25060502-A11&reverse_container_id=CID-REV-001&reverse_sub_tab=materials&reverse_workcenter_groups=WB&reverse_workcenter_groups=DB');

    const { default: QueryToolApp } = await import('../../src/query-tool/App.vue');

    shallowMount(QueryToolApp, {
      global: {
        stubs: {
          PageHeader: true,
          EquipmentView: true,
          LotEquipmentView: true,
          LotTraceView: true,
          SerialReverseTraceView: true,
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(useLotResolveMock).toHaveBeenNthCalledWith(2, expect.objectContaining({
      inputType: 'gd_lot_id',
      inputText: 'GD25060502-A11',
    }));
    expect(useLotDetailMock).toHaveBeenNthCalledWith(2, expect.objectContaining({
      selectedContainerId: 'CID-REV-001',
      activeSubTab: 'materials',
      workcenterGroups: ['WB', 'DB'],
    }));
    expect(reverseLineageState.selectNode).toHaveBeenCalledWith('CID-REV-001');
    expect(reverseDetailState.setSelectedContainerId).toHaveBeenCalledWith('CID-REV-001');
  });

  it('syncs reverse workcenter groups back into runtime URL', async () => {
    window.history.replaceState({}, '', '/query-tool?tab=reverse&reverse_input_type=serial_number&reverse_values=SN-001');

    const { default: QueryToolApp } = await import('../../src/query-tool/App.vue');

    shallowMount(QueryToolApp, {
      global: {
        stubs: {
          PageHeader: true,
          EquipmentView: true,
          LotEquipmentView: true,
          LotTraceView: true,
          SerialReverseTraceView: true,
        },
      },
    });

    replaceRuntimeHistoryMock.mockClear();
    reverseDetailState.selectedWorkcenterGroups.value = ['WB'];

    await nextTick();
    await nextTick();

    expect(replaceRuntimeHistoryMock).toHaveBeenCalled();
    const latestUrl = replaceRuntimeHistoryMock.mock.calls.at(-1)?.[0] || '';
    expect(latestUrl).toContain('/query-tool?');
    expect(latestUrl).toContain('tab=reverse');
    expect(latestUrl).toContain('reverse_workcenter_groups=WB');
  });

  it('restores equipment deep-link state from URL on mount', async () => {
    window.history.replaceState(
      {},
      '',
      '/query-tool?tab=equipment&equipment_ids=EQ-01&equipment_ids=EQ-02&start_date=2026-03-01&end_date=2026-03-07&equipment_sub_tab=jobs',
    );

    const { default: QueryToolApp } = await import('../../src/query-tool/App.vue');

    shallowMount(QueryToolApp, {
      global: {
        stubs: {
          PageHeader: true,
          EquipmentView: true,
          LotEquipmentView: true,
          LotTraceView: true,
          SerialReverseTraceView: true,
        },
      },
    });

    await nextTick();
    await nextTick();

    expect(useEquipmentQueryMock).toHaveBeenCalledWith(expect.objectContaining({
      selectedEquipmentIds: ['EQ-01', 'EQ-02'],
      startDate: '2026-03-01',
      endDate: '2026-03-07',
      activeSubTab: 'jobs',
    }));
    expect(equipmentQueryState.selectedEquipmentIds.value).toEqual(['EQ-01', 'EQ-02']);
    expect(equipmentQueryState.startDate.value).toBe('2026-03-01');
    expect(equipmentQueryState.endDate.value).toBe('2026-03-07');
    expect(equipmentQueryState.activeSubTab.value).toBe('jobs');
  });

  it('syncs lot-equipment state back into runtime URL', async () => {
    window.history.replaceState(
      {},
      '',
      '/query-tool?tab=lot_equipment&le_input_type=lot_id&le_input_text=LOT-001&le_sub_tab=jobs',
    );

    const { default: QueryToolApp } = await import('../../src/query-tool/App.vue');

    shallowMount(QueryToolApp, {
      global: {
        stubs: {
          PageHeader: true,
          EquipmentView: true,
          LotEquipmentView: true,
          LotTraceView: true,
          SerialReverseTraceView: true,
        },
      },
    });

    expect(useLotEquipmentQueryMock).toHaveBeenCalledWith(expect.objectContaining({
      inputType: 'lot_id',
      inputText: 'LOT-001',
      activeSubTab: 'jobs',
    }));

    replaceRuntimeHistoryMock.mockClear();
    lotEquipmentQueryState.selectedWorkcenterGroups.value = ['WB', 'DB'];
    lotEquipmentQueryState.activeSubTab.value = 'rejects';

    await nextTick();
    await nextTick();

    expect(replaceRuntimeHistoryMock).toHaveBeenCalled();
    const latestUrl = replaceRuntimeHistoryMock.mock.calls.at(-1)?.[0] || '';
    expect(latestUrl).toContain('/query-tool?');
    expect(latestUrl).toContain('tab=lot_equipment');
    expect(latestUrl).toContain('le_input_text=LOT-001');
    expect(latestUrl).toContain('le_workcenter_groups=WB');
    expect(latestUrl).toContain('le_workcenter_groups=DB');
    expect(latestUrl).toContain('le_sub_tab=rejects');
  });
});
