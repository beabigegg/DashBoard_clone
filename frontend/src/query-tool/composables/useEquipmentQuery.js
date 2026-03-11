import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { exportCsv } from '../utils/csv.js';
import { normalizeText, toDateInputValue, uniqueValues } from '../utils/values.js';

const EQUIPMENT_SUB_TABS = Object.freeze(['lots', 'jobs', 'rejects', 'timeline']);
const DEFAULT_LOTS_PER_PAGE = 200;

function normalizeSubTab(value) {
  const tab = normalizeText(value).toLowerCase();
  return EQUIPMENT_SUB_TABS.includes(tab) ? tab : 'lots';
}

function defaultDateRange(days = 30) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - Number(days || 30));
  return {
    startDate: toDateInputValue(start),
    endDate: toDateInputValue(end),
  };
}

function emptyTabFlags() {
  return {
    lots: false,
    jobs: false,
    rejects: false,
    timeline: false,
    status_hours: false,
  };
}

export function useEquipmentQuery(initial = {}) {
  ensureMesApiAvailable();

  const equipmentOptions = ref([]);

  const selectedEquipmentIds = ref(uniqueValues(initial.selectedEquipmentIds || []));
  const activeSubTab = ref(normalizeSubTab(initial.activeSubTab));

  const rangeDefaults = defaultDateRange();
  const startDate = ref(normalizeText(initial.startDate) || rangeDefaults.startDate);
  const endDate = ref(normalizeText(initial.endDate) || rangeDefaults.endDate);

  const lotsRows = ref([]);
  const lotsPagination = ref({ page: 1, per_page: DEFAULT_LOTS_PER_PAGE, total: 0, total_pages: 1 });
  const jobsRows = ref([]);
  const rejectsRows = ref([]);
  const statusRows = ref([]);

  const loading = reactive({
    bootstrapping: false,
    lots: false,
    jobs: false,
    rejects: false,
    timeline: false,
    status_hours: false,
  });

  const errors = reactive({
    equipmentOptions: '',
    filters: '',
    lots: '',
    jobs: '',
    rejects: '',
    timeline: '',
    status_hours: '',
  });

  const queried = reactive(emptyTabFlags());
  const exporting = reactive(emptyTabFlags());

  const selectedEquipmentNames = computed(() => {
    const selectedSet = new Set(selectedEquipmentIds.value);
    return equipmentOptions.value
      .filter((item) => selectedSet.has(String(item.RESOURCEID)))
      .map((item) => item.RESOURCENAME)
      .filter(Boolean);
  });

  const equipmentOptionItems = computed(() => {
    return equipmentOptions.value.map((item) => ({
      value: String(item.RESOURCEID),
      label: item.RESOURCENAME || String(item.RESOURCEID),
    }));
  });

  function resetDateRange(days = 30) {
    const defaults = defaultDateRange(days);
    startDate.value = defaults.startDate;
    endDate.value = defaults.endDate;
  }

  function validateFilters() {
    if (selectedEquipmentIds.value.length === 0) {
      return '請選擇至少一台設備';
    }
    if (!startDate.value || !endDate.value) {
      return '請指定日期範圍';
    }
    return '';
  }

  function buildQueryPayload(queryType, options = {}) {
    const payload = {
      equipment_ids: selectedEquipmentIds.value,
      equipment_names: selectedEquipmentNames.value,
      start_date: startDate.value,
      end_date: endDate.value,
      query_type: queryType,
    };
    if (queryType === 'lots') {
      payload.page = Number(options.page || lotsPagination.value.page || 1);
      payload.per_page = Number(options.perPage || lotsPagination.value.per_page || DEFAULT_LOTS_PER_PAGE);
    }
    return payload;
  }

  async function fetchEquipmentPeriod(queryType, options = {}) {
    const validation = validateFilters();
    if (validation) {
      throw new Error(validation);
    }

    const payload = await apiPost(
      '/api/query-tool/equipment-period',
      buildQueryPayload(queryType, options),
      { timeout: 360000, silent: true },
    );

    return payload?.data || {};
  }

  async function loadEquipmentOptions() {
    loading.bootstrapping = true;
    errors.equipmentOptions = '';

    try {
      const payload = await apiGet('/api/query-tool/equipment-list', {
        timeout: 360000,
        silent: true,
      });
      const inner = payload?.data || {};
      equipmentOptions.value = Array.isArray(inner?.data) ? inner.data : [];
      return true;
    } catch (error) {
      errors.equipmentOptions = error?.message || '載入設備清單失敗';
      equipmentOptions.value = [];
      return false;
    } finally {
      loading.bootstrapping = false;
    }
  }

  async function queryLots({ page = null } = {}) {
    loading.lots = true;
    errors.filters = '';
    errors.lots = '';

    try {
      const payload = await fetchEquipmentPeriod('lots', { page, perPage: DEFAULT_LOTS_PER_PAGE });
      lotsRows.value = Array.isArray(payload?.data) ? payload.data : [];
      lotsPagination.value = payload?.pagination || {
        page: Number(page || 1),
        per_page: DEFAULT_LOTS_PER_PAGE,
        total: lotsRows.value.length,
        total_pages: 1,
      };
      queried.lots = true;
      return true;
    } catch (error) {
      errors.lots = error?.message || '查詢生產紀錄失敗';
      if (!errors.filters) {
        errors.filters = errors.lots;
      }
      lotsRows.value = [];
      lotsPagination.value = { page: 1, per_page: DEFAULT_LOTS_PER_PAGE, total: 0, total_pages: 1 };
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
      if (!errors.filters) {
        errors.filters = errors.jobs;
      }
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
      if (!errors.filters) {
        errors.filters = errors.rejects;
      }
      rejectsRows.value = [];
      return false;
    } finally {
      loading.rejects = false;
    }
  }

  async function queryTimeline() {
    loading.timeline = true;
    loading.status_hours = true;
    errors.filters = '';
    errors.timeline = '';
    errors.status_hours = '';

    try {
      const [statusData, lotsData, jobsData] = await Promise.all([
        fetchEquipmentPeriod('status_hours'),
        fetchEquipmentPeriod('lots', { page: 1, perPage: DEFAULT_LOTS_PER_PAGE }),
        fetchEquipmentPeriod('jobs'),
      ]);

      statusRows.value = Array.isArray(statusData?.data) ? statusData.data : [];
      lotsRows.value = Array.isArray(lotsData?.data) ? lotsData.data : [];
      jobsRows.value = Array.isArray(jobsData?.data) ? jobsData.data : [];
      lotsPagination.value = lotsData?.pagination || {
        page: 1,
        per_page: DEFAULT_LOTS_PER_PAGE,
        total: lotsRows.value.length,
        total_pages: 1,
      };

      queried.timeline = true;
      queried.status_hours = true;
      queried.lots = true;
      queried.jobs = true;

      return true;
    } catch (error) {
      const message = error?.message || '查詢設備 Timeline 失敗';
      errors.timeline = message;
      errors.status_hours = message;
      if (!errors.filters) {
        errors.filters = message;
      }
      statusRows.value = [];
      lotsPagination.value = { page: 1, per_page: DEFAULT_LOTS_PER_PAGE, total: 0, total_pages: 1 };
      return false;
    } finally {
      loading.timeline = false;
      loading.status_hours = false;
    }
  }

  async function queryActiveSubTab() {
    const tab = activeSubTab.value;
    if (tab === 'lots') {
      return queryLots();
    }
    if (tab === 'jobs') {
      return queryJobs();
    }
    if (tab === 'rejects') {
      return queryRejects();
    }
    return queryTimeline();
  }

  async function setActiveSubTab(tab, { autoQuery = true } = {}) {
    activeSubTab.value = normalizeSubTab(tab);
    if (!autoQuery) {
      return true;
    }
    return queryActiveSubTab();
  }

  function setSelectedEquipmentIds(ids = []) {
    selectedEquipmentIds.value = uniqueValues(ids);
  }

  function canExportSubTab(tab) {
    const normalized = normalizeSubTab(tab);
    if (normalized === 'lots') {
      return lotsRows.value.length > 0;
    }
    if (normalized === 'jobs') {
      return jobsRows.value.length > 0;
    }
    if (normalized === 'rejects') {
      return rejectsRows.value.length > 0;
    }
    return statusRows.value.length > 0;
  }

  async function exportSubTab(tab) {
    const normalized = normalizeSubTab(tab);

    if (!canExportSubTab(normalized)) {
      return false;
    }

    exporting[normalized] = true;

    try {
      let exportType = 'equipment_lots';
      const params = {
        equipment_ids: selectedEquipmentIds.value,
        equipment_names: selectedEquipmentNames.value,
        start_date: startDate.value,
        end_date: endDate.value,
      };

      if (normalized === 'jobs') {
        exportType = 'equipment_jobs';
      } else if (normalized === 'rejects') {
        exportType = 'equipment_rejects';
      } else if (normalized === 'timeline') {
        exportType = 'equipment_status_hours';
      }

      await exportCsv({
        exportType,
        params,
      });

      return true;
    } catch (error) {
      const message = error?.message || '匯出失敗';
      errors[normalized] = message;
      return false;
    } finally {
      exporting[normalized] = false;
    }
  }

  async function bootstrap() {
    if (!startDate.value || !endDate.value) {
      resetDateRange(30);
    }
    return loadEquipmentOptions();
  }

  return {
    equipmentSubTabs: EQUIPMENT_SUB_TABS,
    equipmentOptions,
    equipmentOptionItems,
    selectedEquipmentIds,
    selectedEquipmentNames,
    startDate,
    endDate,
    activeSubTab,
    lotsRows,
    lotsPagination,
    jobsRows,
    rejectsRows,
    statusRows,
    loading,
    errors,
    queried,
    exporting,
    bootstrap,
    resetDateRange,
    setSelectedEquipmentIds,
    setActiveSubTab,
    queryLots,
    queryJobs,
    queryRejects,
    queryTimeline,
    queryActiveSubTab,
    canExportSubTab,
    exportSubTab,
  };
}
