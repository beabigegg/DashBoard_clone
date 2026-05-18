import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api';
import { exportCsv } from '../utils/csv';
import { normalizeText, parseInputValues } from '../utils/values';

interface LotEquipmentQueryInitial {
  inputType?: string;
  inputText?: string;
  workcenterGroups?: string[];
  activeSubTab?: string;
}

const EQUIPMENT_SUB_TABS = Object.freeze(['lots', 'jobs', 'rejects']);
const DEFAULT_LOTS_PER_PAGE = 25;
const PAGE_SIZE_OPTIONS = Object.freeze([25, 50, 100, 200]);
const MAX_INPUT = 100;

const INPUT_TYPE_OPTIONS = Object.freeze([
  { value: 'lot_id', label: 'LOT ID' },
  { value: 'work_order', label: '工單' },
]);

function normalizeSubTab(value: unknown): string {
  const tab = normalizeText(value).toLowerCase();
  return EQUIPMENT_SUB_TABS.includes(tab) ? tab : 'lots';
}

function normalizeInputType(value: unknown): string {
  const text = normalizeText(value);
  return INPUT_TYPE_OPTIONS.some((opt) => opt.value === text) ? text : 'lot_id';
}

export function useLotEquipmentQuery(initial: LotEquipmentQueryInitial = {}) {
  ensureMesApiAvailable();

  // ── Input state ──
  const inputType = ref(normalizeInputType(initial.inputType));
  const inputText = ref(normalizeText(initial.inputText));
  const workcenterGroups = ref<Array<{ name: string; [key: string]: unknown }>>([]);
  const selectedWorkcenterGroups = ref(
    Array.isArray(initial.workcenterGroups) ? initial.workcenterGroups.filter(Boolean) : [],
  );

  // ── Resolved equipment ──
  const resolvedEquipmentIds = ref<string[]>([]);
  const resolvedEquipmentNames = ref<string[]>([]);
  const resolvedLotNames = ref<string[]>([]);
  const startDate = ref('');
  const endDate = ref('');
  const lookupMessage = ref('');
  const traceMap = ref<Record<string, string>>({});

  // ── Sub-tab data (same as useEquipmentQuery) ──
  const activeSubTab = ref(normalizeSubTab(initial.activeSubTab));
  const _allLotsRows = ref<Record<string, unknown>[]>([]);
  const _lotsPerPage = ref(DEFAULT_LOTS_PER_PAGE);
  const _lotsCurrentPage = ref(1);

  const lotsRows = computed(() => {
    const start = (_lotsCurrentPage.value - 1) * _lotsPerPage.value;
    return _allLotsRows.value.slice(start, start + _lotsPerPage.value);
  });

  const lotsPagination = computed(() => {
    const total = _allLotsRows.value.length;
    const perPage = _lotsPerPage.value;
    return {
      page: _lotsCurrentPage.value,
      per_page: perPage,
      total,
      total_pages: Math.max(1, Math.ceil(total / perPage)),
    };
  });
  const jobsRows = ref<Record<string, unknown>[]>([]);
  const rejectsRows = ref<Record<string, unknown>[]>([]);

  const loading = reactive({
    bootstrapping: false,
    lookup: false,
    lots: false,
    jobs: false,
    rejects: false,
  });

  const errors = reactive({
    workcenterGroups: '',
    lookup: '',
    filters: '',
    lots: '',
    jobs: '',
    rejects: '',
  });

  const queried = reactive({
    lots: false,
    jobs: false,
    rejects: false,
  });

  const exporting = reactive({
    lots: false,
    jobs: false,
    rejects: false,
  });

  const workcenterGroupOptions = computed(() =>
    workcenterGroups.value.map((g) => ({
      value: g.name,
      label: g.name,
    })),
  );

  const parsedInputCount = computed(() => parseInputValues(inputText.value).length);

  const traceEntries = computed(() => {
    const map = traceMap.value;
    if (!map || typeof map !== 'object') return [];
    return Object.entries(map).map(([from, to]) => ({ from, to }));
  });

  // ── Bootstrap: load workcenter groups ──

  async function bootstrap() {
    loading.bootstrapping = true;
    errors.workcenterGroups = '';

    try {
      const payload = await apiGet('/api/query-tool/workcenter-groups', {
        timeout: 360000,
        silent: true,
      });
      const inner = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
      workcenterGroups.value = Array.isArray(inner?.data) ? inner.data : [];
      return true;
    } catch (error) {
      errors.workcenterGroups = (error as Error)?.message || '載入站點群組失敗';
      workcenterGroups.value = [];
      return false;
    } finally {
      loading.bootstrapping = false;
    }
  }

  // ── Lookup ──

  function validateLookup() {
    const values = parseInputValues(inputText.value);
    if (values.length === 0) {
      return inputType.value === 'work_order' ? '請輸入至少一筆工單' : '請輸入至少一筆 LOT ID';
    }
    if (values.length > MAX_INPUT) {
      return `輸入數量不得超過 ${MAX_INPUT} 筆`;
    }
    if (!selectedWorkcenterGroups.value || selectedWorkcenterGroups.value.length === 0) {
      return '請選擇站點群組';
    }
    return '';
  }

  function clearResults() {
    resolvedEquipmentIds.value = [];
    resolvedEquipmentNames.value = [];
    resolvedLotNames.value = [];
    startDate.value = '';
    endDate.value = '';
    lookupMessage.value = '';
    traceMap.value = {};
    _allLotsRows.value = [];
    _lotsCurrentPage.value = 1;
    jobsRows.value = [];
    rejectsRows.value = [];
    Object.keys(queried).forEach((k) => { (queried as Record<string, boolean>)[k] = false; });
  }

  async function lookupEquipment() {
    const validation = validateLookup();
    if (validation) {
      errors.lookup = validation;
      return false;
    }

    loading.lookup = true;
    errors.lookup = '';
    errors.filters = '';
    lookupMessage.value = '';
    clearResults();

    try {
      const values = parseInputValues(inputText.value);
      const payload = await apiPost('/api/query-tool/lot-equipment-lookup', {
        input_type: inputType.value,
        values,
        workcenter_groups: selectedWorkcenterGroups.value,
      }, { timeout: 360000, silent: true });

      const result = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
      resolvedEquipmentIds.value = Array.isArray(result.equipment_ids) ? result.equipment_ids as string[] : [];
      resolvedEquipmentNames.value = Array.isArray(result.equipment_names) ? result.equipment_names as string[] : [];
      resolvedLotNames.value = (Array.isArray(result.lot_names) ? result.lot_names as string[] : []).map((n) => String(n).toUpperCase());
      traceMap.value = (result.trace_map && typeof result.trace_map === 'object') ? result.trace_map as Record<string, string> : {};

      if (resolvedEquipmentIds.value.length === 0) {
        lookupMessage.value = (result.not_found_hint as string) || '在指定站點群組中找不到這些批次的設備紀錄';
        return false;
      }

      const dateRange = result.date_range as Record<string, string> | null | undefined;
      if (dateRange) {
        startDate.value = dateRange.start || '';
        endDate.value = dateRange.end || '';
      }

      lookupMessage.value = `找到 ${resolvedEquipmentIds.value.length} 台設備`;

      // Auto-query active sub-tab
      await queryActiveSubTab();
      return true;
    } catch (error) {
      errors.lookup = (error as Error)?.message || '查詢失敗';
      return false;
    } finally {
      loading.lookup = false;
    }
  }

  // ── Data queries (reuse equipment-period API) ──

  function buildQueryPayload(queryType: string, options: { page?: number | null; perPage?: number | null } = {}): Record<string, unknown> {
    return {
      equipment_ids: resolvedEquipmentIds.value,
      equipment_names: resolvedEquipmentNames.value,
      start_date: startDate.value,
      end_date: endDate.value,
      query_type: queryType,
      ...(queryType === 'lots' ? {
        page: Number(options.page || lotsPagination.value.page || 1),
        per_page: Number(options.perPage || DEFAULT_LOTS_PER_PAGE),
      } : {}),
    };
  }

  async function fetchEquipmentPeriod(queryType: string, options: { page?: number | null; perPage?: number | null } = {}): Promise<Record<string, unknown>> {
    if (resolvedEquipmentIds.value.length === 0) {
      throw new Error('請先查詢批次對應的設備');
    }

    const payload = await apiPost(
      '/api/query-tool/equipment-period',
      buildQueryPayload(queryType, options),
      { timeout: 360000, silent: true },
    );
    return (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
  }

  async function queryLots() {
    loading.lots = true;
    errors.filters = '';
    errors.lots = '';

    try {
      const payload = await fetchEquipmentPeriod('lots', { page: 1, perPage: 9999 });
      const allRows = Array.isArray(payload?.data) ? payload.data : [];
      const relevant = new Set(resolvedLotNames.value);
      _allLotsRows.value = relevant.size > 0
        ? allRows.filter((row) => relevant.has(String(row.CONTAINERNAME || '').toUpperCase()))
        : allRows;
      _lotsCurrentPage.value = 1;
      queried.lots = true;
      return true;
    } catch (error) {
      errors.lots = (error as Error)?.message || '查詢生產紀錄失敗';
      _allLotsRows.value = [];
      return false;
    } finally {
      loading.lots = false;
    }
  }

  function changeLotsPage(page: unknown): void {
    const p = Number(page);
    if (!Number.isNaN(p) && p >= 1 && p <= lotsPagination.value.total_pages) {
      _lotsCurrentPage.value = p;
    }
  }

  function changeLotsPerPage(perPage: unknown): void {
    _lotsPerPage.value = Number(perPage) || DEFAULT_LOTS_PER_PAGE;
    _lotsCurrentPage.value = 1;
  }

  async function queryJobs() {
    loading.jobs = true;
    errors.filters = '';
    errors.jobs = '';

    try {
      const payload = await fetchEquipmentPeriod('jobs');
      const allRows = Array.isArray(payload?.data) ? payload.data : [];
      const relevant = new Set(resolvedLotNames.value);
      jobsRows.value = relevant.size > 0
        ? allRows.filter((row) => {
            const names = String(row.CONTAINERNAMES || '').toUpperCase();
            return [...relevant].some((n) => names.includes(n));
          })
        : allRows;
      queried.jobs = true;
      return true;
    } catch (error) {
      errors.jobs = (error as Error)?.message || '查詢維修紀錄失敗';
      jobsRows.value = [];
      return false;
    } finally {
      loading.jobs = false;
    }
  }

  async function queryRejects() {
    loading.rejects = true;
    errors.filters = '';
    errors.rejects = '';

    try {
      const payload = await fetchEquipmentPeriod('rejects');
      rejectsRows.value = Array.isArray(payload?.data) ? payload.data : [];
      queried.rejects = true;
      return true;
    } catch (error) {
      errors.rejects = (error as Error)?.message || '查詢報廢紀錄失敗';
      rejectsRows.value = [];
      return false;
    } finally {
      loading.rejects = false;
    }
  }

  async function queryActiveSubTab() {
    const tab = activeSubTab.value;
    if (tab === 'lots') return queryLots();
    if (tab === 'jobs') return queryJobs();
    return queryRejects();
  }

  async function setActiveSubTab(tab: unknown): Promise<boolean> {
    activeSubTab.value = normalizeSubTab(tab);
    if (resolvedEquipmentIds.value.length > 0) {
      return queryActiveSubTab();
    }
    return true;
  }

  function canExportSubTab(tab: unknown): boolean {
    const normalized = normalizeSubTab(tab);
    if (normalized === 'lots') return _allLotsRows.value.length > 0;
    if (normalized === 'jobs') return jobsRows.value.length > 0;
    if (normalized === 'rejects') return rejectsRows.value.length > 0;
    return lotsRows.value.length > 0;
  }

  async function exportSubTab(tab: unknown): Promise<boolean> {
    const normalized = normalizeSubTab(tab);
    if (!canExportSubTab(normalized)) return false;

    const exportingMap = exporting as Record<string, boolean>;
    const errorsMap = errors as Record<string, string>;
    exportingMap[normalized] = true;
    try {
      let exportType = 'equipment_lots';
      if (normalized === 'jobs') exportType = 'equipment_jobs';
      else if (normalized === 'rejects') exportType = 'equipment_rejects';

      await exportCsv({
        exportType,
        params: {
          equipment_ids: resolvedEquipmentIds.value,
          equipment_names: resolvedEquipmentNames.value,
          start_date: startDate.value,
          end_date: endDate.value,
        },
      });
      return true;
    } catch (error) {
      errorsMap[normalized] = (error as Error)?.message || '匯出失敗';
      return false;
    } finally {
      exportingMap[normalized] = false;
    }
  }

  return {
    inputType,
    inputTypeOptions: INPUT_TYPE_OPTIONS,
    inputText,
    parsedInputCount,
    workcenterGroups,
    workcenterGroupOptions,
    selectedWorkcenterGroups,
    resolvedEquipmentIds,
    resolvedEquipmentNames,
    startDate,
    endDate,
    lookupMessage,
    traceMap,
    traceEntries,
    activeSubTab,
    lotsRows,
    lotsPagination,
    jobsRows,
    rejectsRows,
    loading,
    errors,
    queried,
    exporting,
    bootstrap,
    lookupEquipment,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    queryLots,
    queryJobs,
    queryRejects,
    queryActiveSubTab,
    setActiveSubTab,
    changeLotsPage,
    changeLotsPerPage,
    canExportSubTab,
    exportSubTab,
    clearResults,
  };
}
