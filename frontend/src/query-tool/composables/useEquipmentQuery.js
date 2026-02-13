import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api.js';
import { exportCsv } from '../utils/csv.js';
import { normalizeText, toDateInputValue, uniqueValues } from '../utils/values.js';

const EQUIPMENT_SUB_TABS = Object.freeze(['lots', 'jobs', 'rejects', 'timeline']);

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
      label: item.RESOURCENAME ? `${item.RESOURCENAME} (${item.RESOURCEID})` : String(item.RESOURCEID),
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

  function buildQueryPayload(queryType) {
    return {
      equipment_ids: selectedEquipmentIds.value,
      equipment_names: selectedEquipmentNames.value,
      start_date: startDate.value,
      end_date: endDate.value,
      query_type: queryType,
    };
  }

  async function fetchEquipmentPeriod(queryType) {
    const validation = validateFilters();
    if (validation) {
      throw new Error(validation);
    }

    const payload = await apiPost(
      '/api/query-tool/equipment-period',
      buildQueryPayload(queryType),
      { timeout: 120000, silent: true },
    );

    return Array.isArray(payload?.data) ? payload.data : [];
  }

  async function loadEquipmentOptions() {
    loading.bootstrapping = true;
    errors.equipmentOptions = '';

    try {
      const payload = await apiGet('/api/query-tool/equipment-list', {
        timeout: 60000,
        silent: true,
      });
      equipmentOptions.value = Array.isArray(payload?.data) ? payload.data : [];
      return true;
    } catch (error) {
      errors.equipmentOptions = error?.message || '載入設備清單失敗';
      equipmentOptions.value = [];
      return false;
    } finally {
      loading.bootstrapping = false;
    }
  }

  async function queryLots() {
    loading.lots = true;
    errors.filters = '';
    errors.lots = '';

    try {
      lotsRows.value = await fetchEquipmentPeriod('lots');
      queried.lots = true;
      return true;
    } catch (error) {
      errors.lots = error?.message || '查詢生產紀錄失敗';
      if (!errors.filters) {
        errors.filters = errors.lots;
      }
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
      jobsRows.value = await fetchEquipmentPeriod('jobs');
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
      rejectsRows.value = await fetchEquipmentPeriod('rejects');
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
        fetchEquipmentPeriod('lots'),
        fetchEquipmentPeriod('jobs'),
      ]);

      statusRows.value = statusData;
      lotsRows.value = lotsData;
      jobsRows.value = jobsData;

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
