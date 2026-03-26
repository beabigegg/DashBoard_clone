import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { exportCsv } from '../utils/csv.js';
import { normalizeText, parseInputValues } from '../utils/values.js';

const EQUIPMENT_SUB_TABS = Object.freeze(['lots', 'jobs', 'rejects']);
const DEFAULT_LOTS_PER_PAGE = 200;
const MAX_INPUT = 100;

const INPUT_TYPE_OPTIONS = Object.freeze([
  { value: 'lot_id', label: 'LOT ID' },
  { value: 'work_order', label: '工單' },
]);

function normalizeSubTab(value) {
  const tab = normalizeText(value).toLowerCase();
  return EQUIPMENT_SUB_TABS.includes(tab) ? tab : 'lots';
}

function normalizeInputType(value) {
  const text = normalizeText(value);
  return INPUT_TYPE_OPTIONS.some((opt) => opt.value === text) ? text : 'lot_id';
}

export function useLotEquipmentQuery(initial = {}) {
  ensureMesApiAvailable();

  // ── Input state ──
  const inputType = ref(normalizeInputType(initial.inputType));
  const inputText = ref(normalizeText(initial.inputText));
  const workcenterGroups = ref([]);
  const selectedWorkcenterGroups = ref(
    Array.isArray(initial.workcenterGroups) ? initial.workcenterGroups.filter(Boolean) : [],
  );

  // ── Resolved equipment ──
  const resolvedEquipmentIds = ref([]);
  const resolvedEquipmentNames = ref([]);
  const startDate = ref('');
  const endDate = ref('');
  const lookupMessage = ref('');
  const traceMap = ref({});

  // ── Sub-tab data (same as useEquipmentQuery) ──
  const activeSubTab = ref(normalizeSubTab(initial.activeSubTab));
  const lotsRows = ref([]);
  const lotsPagination = ref({ page: 1, per_page: DEFAULT_LOTS_PER_PAGE, total: 0, total_pages: 1 });
  const jobsRows = ref([]);
  const rejectsRows = ref([]);

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

  /** Set of lot names relevant to the query (input lots + traced parent lots).
   *  For work_order input, the input values are work order names (not lot names),
   *  so we rely on traceMap keys (resolved lot names) instead. */
  const relevantLotNames = computed(() => {
    const names = new Set();
    // For lot input, include input values directly; for work_order, skip (work order != lot name)
    if (inputType.value !== 'work_order') {
      parseInputValues(inputText.value).forEach((v) => names.add(v.toUpperCase()));
    }
    const map = traceMap.value;
    if (map && typeof map === 'object') {
      // Include both resolved lot names (keys) and their parent lot names (values)
      Object.entries(map).forEach(([lotName, parentName]) => {
        if (lotName) names.add(String(lotName).toUpperCase());
        if (parentName) names.add(String(parentName).toUpperCase());
      });
    }
    return names;
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
      const inner = payload?.data || {};
      workcenterGroups.value = Array.isArray(inner?.data) ? inner.data : [];
      return true;
    } catch (error) {
      errors.workcenterGroups = error?.message || '載入站點群組失敗';
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
    startDate.value = '';
    endDate.value = '';
    lookupMessage.value = '';
    traceMap.value = {};
    lotsRows.value = [];
    lotsPagination.value = { page: 1, per_page: DEFAULT_LOTS_PER_PAGE, total: 0, total_pages: 1 };
    jobsRows.value = [];
    rejectsRows.value = [];
    Object.keys(queried).forEach((k) => { queried[k] = false; });
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

      const result = payload?.data || {};
      resolvedEquipmentIds.value = result.equipment_ids || [];
      resolvedEquipmentNames.value = result.equipment_names || [];
      traceMap.value = result.trace_map || {};

      if (resolvedEquipmentIds.value.length === 0) {
        lookupMessage.value = result.not_found_hint || '在指定站點群組中找不到這些批次的設備紀錄';
        return false;
      }

      if (result.date_range) {
        startDate.value = result.date_range.start || '';
        endDate.value = result.date_range.end || '';
      }

      lookupMessage.value = `找到 ${resolvedEquipmentIds.value.length} 台設備`;

      // Auto-query active sub-tab
      await queryActiveSubTab();
      return true;
    } catch (error) {
      errors.lookup = error?.message || '查詢失敗';
      return false;
    } finally {
      loading.lookup = false;
    }
  }

  // ── Data queries (reuse equipment-period API) ──

  function buildQueryPayload(queryType, options = {}) {
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

  async function fetchEquipmentPeriod(queryType, options = {}) {
    if (resolvedEquipmentIds.value.length === 0) {
      throw new Error('請先查詢批次對應的設備');
    }

    const payload = await apiPost(
      '/api/query-tool/equipment-period',
      buildQueryPayload(queryType, options),
      { timeout: 360000, silent: true },
    );
    return payload?.data || {};
  }

  async function queryLots({ page = null } = {}) {
    loading.lots = true;
    errors.filters = '';
    errors.lots = '';

    try {
      // Fetch all lots for the equipment, then filter to only relevant lots
      const payload = await fetchEquipmentPeriod('lots', { page: 1, perPage: 9999 });
      const allRows = Array.isArray(payload?.data) ? payload.data : [];
      const relevant = relevantLotNames.value;
      // When relevant set is empty (e.g., work_order with no trace map), show all lots
      lotsRows.value = relevant.size > 0
        ? allRows.filter((row) => {
            const name = String(row.CONTAINERNAME || '').toUpperCase();
            return relevant.has(name);
          })
        : allRows;
      lotsPagination.value = {
        page: 1,
        per_page: lotsRows.value.length,
        total: lotsRows.value.length,
        total_pages: 1,
      };
      queried.lots = true;
      return true;
    } catch (error) {
      errors.lots = error?.message || '查詢生產紀錄失敗';
      lotsRows.value = [];
      return false;
    } finally {
      loading.lots = false;
    }
  }

  async function queryJobs() {
    loading.jobs = true;
    errors.filters = '';
    errors.jobs = '';

    try {
      const payload = await fetchEquipmentPeriod('jobs');
      jobsRows.value = Array.isArray(payload?.data) ? payload.data : [];
      queried.jobs = true;
      return true;
    } catch (error) {
      errors.jobs = error?.message || '查詢維修紀錄失敗';
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
      errors.rejects = error?.message || '查詢報廢紀錄失敗';
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

  async function setActiveSubTab(tab) {
    activeSubTab.value = normalizeSubTab(tab);
    if (resolvedEquipmentIds.value.length > 0) {
      return queryActiveSubTab();
    }
    return true;
  }

  function canExportSubTab(tab) {
    const normalized = normalizeSubTab(tab);
    if (normalized === 'lots') return lotsRows.value.length > 0;
    if (normalized === 'jobs') return jobsRows.value.length > 0;
    if (normalized === 'rejects') return rejectsRows.value.length > 0;
    return lotsRows.value.length > 0;
  }

  async function exportSubTab(tab) {
    const normalized = normalizeSubTab(tab);
    if (!canExportSubTab(normalized)) return false;

    exporting[normalized] = true;
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
      errors[normalized] = error?.message || '匯出失敗';
      return false;
    } finally {
      exporting[normalized] = false;
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
    queryLots,
    queryJobs,
    queryRejects,
    queryActiveSubTab,
    setActiveSubTab,
    canExportSubTab,
    exportSubTab,
    clearResults,
  };
}
