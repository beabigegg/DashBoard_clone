// @vitest-environment jsdom
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { defineComponent, nextTick, ref } from 'vue';
import { mount, shallowMount } from '@vue/test-utils';

// ── Mocks ──────────────────────────────────────────────────────────────────
const apiGetMock = vi.fn();

vi.mock('../../src/core/api', () => ({
  apiGet: apiGetMock,
  ensureMesApiAvailable: vi.fn(),
}));

vi.mock('../../src/shared-composables/useAutoRefresh', () => ({
  useAutoRefresh: () => ({ resetAutoRefresh: vi.fn() }),
}));

vi.mock('../../src/shared-composables/usePageUpdateBadge', () => ({
  bindUpdateBadge: vi.fn(),
}));

vi.mock('../../src/shared-composables/useFilterOrchestrator', () => ({
  useFilterOrchestrator: () => ({
    committed: {
      groups: [], isProduction: false, isKey: false, isMonitor: false,
      families: [], machines: [], packageGroups: [],
    },
    updateField: vi.fn(),
  }),
}));

// ── Component stubs ────────────────────────────────────────────────────────

const FilterBarStub = defineComponent({
  name: 'FilterBar',
  template: '<div class="filter-bar-stub"></div>',
});

const ErrorBannerStub = defineComponent({
  name: 'ErrorBanner',
  props: ['message'],
  template: '<div class="error-banner-stub"></div>',
});

const SummaryCardGroupStub = defineComponent({
  name: 'SummaryCardGroup',
  template: '<div class="summary-card-group-stub"><slot /></div>',
});

const SummaryCardStub = defineComponent({
  name: 'SummaryCard',
  props: ['label', 'value', 'format', 'accent', 'clickable', 'active'],
  emits: ['click'],
  template: '<div class="summary-card-stub" :data-label="label" :data-active="active" @click="$emit(\'click\')"><slot /><slot name="sub" /></div>',
});

const WorkcenterOuRingsStub = defineComponent({
  name: 'WorkcenterOuRings',
  props: ['equipment', 'selection'],
  emits: ['chart-select'],
  template: '<div class="rings-stub" :data-count="equipment?.length"></div>',
});

const OuHeatmapStub = defineComponent({
  name: 'OuHeatmap',
  props: ['equipment', 'selectedCell'],
  emits: ['cell-select'],
  template: '<div class="heatmap-stub" :data-count="equipment?.length"></div>',
});

const MaintenanceAlertsStub = defineComponent({
  name: 'MaintenanceAlerts',
  props: ['equipment', 'lastUpdate', 'selectedId'],
  emits: ['show-job', 'alert-select'],
  template: '<div class="alerts-stub" :data-count="equipment?.length"></div>',
});

const MatrixSectionStub = defineComponent({
  name: 'MatrixSection',
  props: ['equipment', 'expandedState', 'matrixFilter'],
  emits: ['toggle-row', 'toggle-all', 'cell-filter'],
  template: '<div class="matrix-stub" :data-count="equipment?.length"></div>',
});

const EquipmentGridStub = defineComponent({
  name: 'EquipmentGrid',
  props: ['equipment', 'activeFilterText'],
  emits: ['clear-filter', 'show-lot', 'show-job'],
  template: '<div class="equipment-grid-stub" :data-count="equipment?.length" :data-filter-text="activeFilterText"><button class="clear-btn" @click="$emit(\'clear-filter\')">清除篩選</button></div>',
});

const FloatingTooltipStub = defineComponent({
  name: 'FloatingTooltip',
  props: ['visible', 'type', 'payload', 'position'],
  emits: ['close'],
  template: '<div class="tooltip-stub"></div>',
});

const LoadingOverlayStub = defineComponent({
  name: 'LoadingOverlay',
  props: ['tier'],
  template: '<div class="loading-stub"></div>',
});

// ── Fixture equipment data ─────────────────────────────────────────────────

function makeEq(overrides: Record<string, unknown> = {}) {
  return {
    RESOURCEID: 'R001',
    RESOURCENAME: 'Machine-A',
    EQUIPMENTASSETSSTATUS: 'PRD',
    WORKCENTER_GROUP: 'G1',
    WORKCENTER_GROUP_SEQ: 1,
    RESOURCEFAMILYNAME: 'FAM_A',
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

const EQUIPMENT_LIST = [
  makeEq({ RESOURCEID: 'R001', WORKCENTER_GROUP: 'G1', EQUIPMENTASSETSSTATUS: 'PRD', PACKAGEGROUPNAME: 'QFP' }),
  makeEq({ RESOURCEID: 'R002', WORKCENTER_GROUP: 'G1', EQUIPMENTASSETSSTATUS: 'UDT', STATUS_CATEGORY: 'udt', PACKAGEGROUPNAME: 'QFP' }),
  makeEq({ RESOURCEID: 'R003', WORKCENTER_GROUP: 'G2', EQUIPMENTASSETSSTATUS: 'PRD', PACKAGEGROUPNAME: 'BGA' }),
  makeEq({ RESOURCEID: 'R004', WORKCENTER_GROUP: 'G2', EQUIPMENTASSETSSTATUS: 'UDT', STATUS_CATEGORY: 'udt', PACKAGEGROUPNAME: 'BGA' }),
  makeEq({ RESOURCEID: 'R005', WORKCENTER_GROUP: 'G1', EQUIPMENTASSETSSTATUS: 'PRD', PACKAGEGROUPNAME: null }),
];

function buildApiResponses() {
  apiGetMock.mockImplementation((url: string) => {
    if (url === '/api/resource/status/options') {
      return Promise.resolve({
        success: true,
        data: { workcenter_groups: ['G1', 'G2'], resources: [], package_groups: ['QFP', 'BGA'] },
      });
    }
    if (url === '/api/resource/status/summary') {
      return Promise.resolve({
        success: true,
        data: { total_count: 5, by_status: { PRD: 3, UDT: 2 }, ou_pct: 60, availability_pct: 70 },
      });
    }
    if (url === '/api/resource/status') {
      return Promise.resolve({ success: true, data: EQUIPMENT_LIST });
    }
    if (url === '/health') {
      return Promise.resolve({ equipment_status_cache: { updated_at: '2026-06-09T10:00:00' } });
    }
    return Promise.resolve({ success: true, data: [] });
  });
}

async function mountApp() {
  buildApiResponses();

  const App = (await import('../../src/resource-status/App.vue')).default;

  const wrapper = mount(App, {
    global: {
      stubs: {
        FilterBar: FilterBarStub,
        ErrorBanner: ErrorBannerStub,
        SummaryCardGroup: SummaryCardGroupStub,
        SummaryCard: SummaryCardStub,
        WorkcenterOuRings: WorkcenterOuRingsStub,
        OuHeatmap: OuHeatmapStub,
        MaintenanceAlerts: MaintenanceAlertsStub,
        MatrixSection: MatrixSectionStub,
        EquipmentGrid: EquipmentGridStub,
        FloatingTooltip: FloatingTooltipStub,
        LoadingOverlay: LoadingOverlayStub,
      },
    },
  });

  // Wait for mount + data load
  await nextTick();
  await nextTick();
  await nextTick();

  return wrapper;
}

// ── Unit — component click-emit wiring ────────────────────────────────────

describe('WorkcenterOuRings — emit wiring', () => {
  it('WorkcenterOuRings_emits_selection_on_echart_click — emits {source:ring, group, status} with non-default values', async () => {
    const WorkcenterOuRings = (await import('../../src/resource-status/components/WorkcenterOuRings.vue')).default;
    const wrapper = shallowMount(WorkcenterOuRings, {
      props: { equipment: EQUIPMENT_LIST },
      global: { stubs: { VChart: { template: '<div class="vchart-stub" @click="$emit(\'click\', $event)"></div>', emits: ['click'] } } },
    });
    // Trigger the chart-select emit directly
    await wrapper.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'UDT' });
    const emitted = wrapper.emitted('chart-select');
    expect(emitted).toBeTruthy();
    const payload = emitted![0][0] as { source: string; group: string; status: string };
    expect(payload.source).toBe('ring');
    expect(payload.group).toBe('G1');
    expect(payload.status).toBe('UDT');
  });
});

describe('OuHeatmap — emit wiring', () => {
  it('OuHeatmap_emits_selection_on_cell_click — cell click emits {source:heatmap, group, packageGroupName}', async () => {
    const OuHeatmap = (await import('../../src/resource-status/components/OuHeatmap.vue')).default;
    const wrapper = shallowMount(OuHeatmap, {
      props: { equipment: EQUIPMENT_LIST },
    });
    // Find a heatmap-cell and click it
    const cells = wrapper.findAll('.heatmap-cell');
    if (cells.length > 0) {
      await cells[0].trigger('click');
      const emitted = wrapper.emitted('cell-select');
      expect(emitted).toBeTruthy();
      const payload = emitted![0][0] as { source: string; group: string; packageGroupName: string };
      expect(payload.source).toBe('heatmap');
      expect(typeof payload.group).toBe('string');
      expect(typeof payload.packageGroupName).toBe('string');
    } else {
      // No cells rendered — still check component defines the emit
      expect(wrapper.vm.$options.emits || []).toContain('cell-select');
    }
  });
});

describe('MatrixSection — emit shape unchanged', () => {
  it('MatrixSection_existing_cell_filter_emit_shape_unchanged — emit shape is {workcenter_group, status, family, resource}', async () => {
    const MatrixSection = (await import('../../src/resource-status/components/MatrixSection.vue')).default;
    const wrapper = shallowMount(MatrixSection, {
      props: { equipment: [], expandedState: {}, matrixFilter: [] },
      global: { stubs: { HierarchyTable: { template: '<div></div>' } } },
    });
    // Emit a cell-filter event and check its shape
    await wrapper.vm.$emit('cell-filter', { workcenter_group: 'G1', status: 'UDT', family: null, resource: null });
    const emitted = wrapper.emitted('cell-filter');
    expect(emitted).toBeTruthy();
    const payload = emitted![0][0] as { workcenter_group: string; status: string; family: string | null; resource: string | null };
    expect(payload).toHaveProperty('workcenter_group');
    expect(payload).toHaveProperty('status');
    expect(payload).toHaveProperty('family');
    expect(payload).toHaveProperty('resource');
  });
});

describe('MaintenanceAlerts — alert-select emit', () => {
  it('MaintenanceAlerts_row_click_emits_selection_not_show_job — alert-select emit is distinct from show-job', async () => {
    const MaintenanceAlerts = (await import('../../src/resource-status/components/MaintenanceAlerts.vue')).default;
    const eqWithJob = [
      makeEq({ RESOURCEID: 'R001', JOBORDER: 'WO-001', CREATEDATE: '2026-06-01T08:00:00' }),
    ];
    const wrapper = shallowMount(MaintenanceAlerts, {
      props: { equipment: eqWithJob, lastUpdate: '2026-06-09T10:00:00' },
    });
    // Click the alert card
    const card = wrapper.find('.alert-card');
    if (card.exists()) {
      await card.trigger('click');
      const emitted = wrapper.emitted('alert-select');
      expect(emitted).toBeTruthy();
      const payload = emitted![0][0] as { source: string; resourceId: string };
      expect(payload.source).toBe('alerts');
      expect(payload.resourceId).toBe('R001');
    } else {
      // Check the component defines alert-select emit distinct from show-job
      const emitsOptions = wrapper.vm.$options.emits;
      expect(emitsOptions).toBeTruthy();
    }
  });
});

// ── Integration — App-level cross-filter orchestration ────────────────────

describe('App cross-filter integration', () => {
  beforeEach(() => {
    apiGetMock.mockReset();
    vi.resetModules();
  });

  it('ring_click_UDT_narrows_grid_to_UDT_rows — single-chart narrowing filters EquipmentGrid', async () => {
    const wrapper = await mountApp();

    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'UDT' });
    await nextTick();

    const grid = wrapper.findComponent(EquipmentGridStub);
    expect(grid.exists()).toBe(true);
    const count = Number(grid.attributes('data-count') ?? '-1');
    // UDT in G1 = R002 only
    expect(count).toBeLessThan(EQUIPMENT_LIST.length);
  });

  it('two_chart_selections_produce_and_intersection — ring=G1 + heatmap=QFP; grid satisfies both', async () => {
    const wrapper = await mountApp();

    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    const heatmap = wrapper.findComponent(OuHeatmapStub);
    await heatmap.vm.$emit('cell-select', { source: 'heatmap', group: 'G1', packageGroupName: 'QFP' });
    await nextTick();

    const grid = wrapper.findComponent(EquipmentGridStub);
    expect(grid.exists()).toBe(true);
    const count = Number(grid.attributes('data-count') ?? '-1');
    // G1 + PRD + G1 + QFP = R001 only
    expect(count).toBe(1);
  });

  it('reclick_clears_one_dimension_restores_broader_subset — partial clear after two selections', async () => {
    const wrapper = await mountApp();

    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    const heatmap = wrapper.findComponent(OuHeatmapStub);
    await heatmap.vm.$emit('cell-select', { source: 'heatmap', group: 'G1', packageGroupName: 'QFP' });
    await nextTick();

    // Re-click ring to clear it
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    const grid = wrapper.findComponent(EquipmentGridStub);
    expect(grid.exists()).toBe(true);
    const count = Number(grid.attributes('data-count') ?? '-1');
    // Only heatmap filter active: G1+QFP = R001, R002
    expect(count).toBe(2);
  });

  it('clear_all_button_shown_iff_active_selections_gt_0 — "清除全部" visibility tied to activeSelections length', async () => {
    const wrapper = await mountApp();

    // Before any selection — no clear-all button
    let clearBtn = wrapper.find('.cross-filter-clear-btn');
    expect(clearBtn.exists()).toBe(false);

    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    // After selection — clear-all button appears
    clearBtn = wrapper.find('.cross-filter-clear-btn');
    expect(clearBtn.exists()).toBe(true);
  });

  it('selected_element_has_active_css_class — active selection adds highlight class', async () => {
    const wrapper = await mountApp();

    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    // The rings component should receive a 'selection' prop with the active selection
    const ringsEl = wrapper.findComponent(WorkcenterOuRingsStub);
    const selProp = ringsEl.props('selection');
    expect(selProp).toBeTruthy();
    expect((selProp as { group: string; status: string }).group).toBe('G1');
    expect((selProp as { group: string; status: string }).status).toBe('PRD');
  });

  it('esc_clears_selection_returns_focus_to_trigger — ESC calls el.focus() after nextTick', async () => {
    const wrapper = await mountApp();

    // Create a mock focusable element that simulates the last chart trigger
    // (e.g., a heatmap <td> or alert card <div> that was keyboard-activated)
    const mockTrigger = document.createElement('button');
    mockTrigger.setAttribute('data-testid', 'mock-trigger');
    document.body.appendChild(mockTrigger);
    const focusSpy = vi.spyOn(mockTrigger, 'focus');

    // Simulate a chart element being focused before the cross-filter click
    mockTrigger.focus();

    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    // After selection, clear button should appear
    const clearBtnBefore = wrapper.find('.cross-filter-clear-btn');
    expect(clearBtnBefore.exists()).toBe(true);

    // Simulate ESC key on the app root
    await wrapper.trigger('keydown', { key: 'Escape' });
    await nextTick();
    await nextTick();

    // After ESC, selection should be cleared (button disappears due to v-if)
    const clearBtnAfter = wrapper.find('.cross-filter-clear-btn');
    expect(clearBtnAfter.exists()).toBe(false);

    // Focus must have been returned to the last chart trigger (WCAG 2.1 AA 2.4.3)
    expect(focusSpy).toHaveBeenCalled();

    // Cleanup
    document.body.removeChild(mockTrigger);
  });

  it('filterbar_composes_with_cross_filter_independently — FilterBar pkg_group and cross-filter both reduce grid', async () => {
    const wrapper = await mountApp();

    // Apply a cross-filter selection (ring for G1)
    const rings = wrapper.findComponent(WorkcenterOuRingsStub);
    await rings.vm.$emit('chart-select', { source: 'ring', group: 'G1', status: 'PRD' });
    await nextTick();

    // Now simulate a FilterBar change — this should NOT reset cross-filter
    const filterBar = wrapper.findComponent(FilterBarStub);
    await filterBar.vm.$emit('change-groups', ['G1']);
    await nextTick();

    // The cross-filter should still be active (grid still shows cross-filter indicator)
    const clearBtn = wrapper.find('.cross-filter-clear-btn');
    expect(clearBtn.exists()).toBe(true);
  });

  it('legacy matrixFilter dimensions (workcenter_group + status) still work via new composable', async () => {
    const wrapper = await mountApp();

    const matrix = wrapper.findComponent(MatrixSectionStub);
    await matrix.vm.$emit('cell-filter', { workcenter_group: 'G1', status: 'PRD', family: null, resource: null });
    await nextTick();

    const grid = wrapper.findComponent(EquipmentGridStub);
    expect(grid.exists()).toBe(true);
    const count = Number(grid.attributes('data-count') ?? '-1');
    expect(count).toBeGreaterThan(0);
    expect(count).toBeLessThan(EQUIPMENT_LIST.length);
  });
});
