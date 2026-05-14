import { computed, reactive, ref } from 'vue';

import { apiGet, apiPost, ensureMesApiAvailable } from '../../core/api';
import { exportCsv } from '../utils/csv';
import { normalizeText, toDateInputValue, uniqueValues } from '../utils/values';

interface EquipmentItem {
  RESOURCEID: string | number;
  RESOURCENAME: string;
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

interface EquipmentQueryInitial {
  selectedEquipmentIds?: string[];
  activeSubTab?: string;
  startDate?: string;
  endDate?: string;
}

const EQUIPMENT_SUB_TABS = Object.freeze(['lots', 'jobs', 'rejects']);
const DEFAULT_LOTS_PER_PAGE = 25;
const PAGE_SIZE_OPTIONS = Object.freeze([25, 50, 100, 200]);

function normalizeSubTab(value: unknown): string {
  const tab = normalizeText(value).toLowerCase();
  return EQUIPMENT_SUB_TABS.includes(tab) ? tab : 'lots';
}

function defaultDateRange(days = 30): { startDate: string; endDate: string } {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - Number(days || 30));
  return {
    startDate: toDateInputValue(start),
    endDate: toDateInputValue(end),
  };
}

function emptyTabFlags(): Record<string, boolean> {
  return {
    lots: false,
    jobs: false,
    rejects: false,
    timeline: false,
  };
}

export function useEquipmentQuery(initial: EquipmentQueryInitial = {}) {
  ensureMesApiAvailable();

  const equipmentOptions = ref<EquipmentItem[]>([]);

  const selectedEquipmentIds = ref(uniqueValues(initial.selectedEquipmentIds || []));
  const activeSubTab = ref(normalizeSubTab(initial.activeSubTab));

  const rangeDefaults = defaultDateRange();
  const startDate = ref(normalizeText(initial.startDate) || rangeDefaults.startDate);
  const endDate = ref(normalizeText(initial.endDate) || rangeDefaults.endDate);

  const lotsRows = ref<Record<string, unknown>[]>([]);
  const lotsPagination = ref<Pagination>({ page: 1, per_page: DEFAULT_LOTS_PER_PAGE, total: 0, total_pages: 1 });
  const jobsRows = ref<Record<string, unknown>[]>([]);
  const rejectsRows = ref<Record<string, unknown>[]>([]);
  const statusRows = ref<Record<string, unknown>[]>([]);

  const loading = reactive({
    bootstrapping: false,
    lots: false,
    jobs: false,
    rejects: false,
  });

  const errors = reactive({
    equipmentOptions: '',
    filters: '',
    lots: '',
    jobs: '',
    rejects: '',
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

  function buildQueryPayload(queryType: string, options: { page?: number | null; perPage?: number | null } = {}): Record<string, unknown> {
    const payload: Record<string, unknown> = {
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

  async function fetchEquipmentPeriod(queryType: string, options: { page?: number | null; perPage?: number | null } = {}): Promise<Record<string, unknown>> {
    const validation = validateFilters();
    if (validation) {
      throw new Error(validation);
    }

    const payload = await apiPost(
      '/api/query-tool/equipment-period',
      buildQueryPayload(queryType, options),
      { timeout: 360000, silent: true },
    );

    return (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
  }

  async function loadEquipmentOptions() {
    loading.bootstrapping = true;
    errors.equipmentOptions = '';

    try {
      const payload = await apiGet('/api/query-tool/equipment-list', {
        timeout: 360000,
        silent: true,
      });
      const inner = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
      equipmentOptions.value = Array.isArray(inner?.data) ? inner.data : [];
      return true;
    } catch (error) {
      errors.equipmentOptions = (error as Error)?.message || '載入設備清單失敗';
      equipmentOptions.value = [];
      return false;
    } finally {
      loading.bootstrapping = false;
    }
  }

  async function queryLots({ page = null, perPage = null }: { page?: number | null; perPage?: number | null } = {}): Promise<boolean> {
    loading.lots = true;
    errors.filters = '';
    errors.lots = '';

    try {
      const payload = await fetchEquipmentPeriod('lots', { page, perPage: perPage ?? lotsPagination.value.per_page });
      lotsRows.value = Array.isArray(payload?.data) ? payload.data as Record<string, unknown>[] : [];
      lotsPagination.value = (payload?.pagination as Pagination) || {
        page: Number(page || 1),
        per_page: DEFAULT_LOTS_PER_PAGE,
        total: lotsRows.value.length,
        total_pages: 1,
      };
      queried.lots = true;
      return true;
    } catch (error) {
      errors.lots = (error as Error)?.message || '查詢生產紀錄失敗';
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
      errors.jobs = (error as Error)?.message || '查詢維修紀錄失敗';
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
      errors.rejects = (error as Error)?.message || '查詢報廢紀錄失敗';
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
    const validation = validateFilters();
    if (validation) {
      errors.filters = validation;
      return false;
    }

    errors.filters = '';

    try {
      const [statusPayload, lotsPayload, jobsPayload] = await Promise.all([
        fetchEquipmentPeriod('status_hours'),
        fetchEquipmentPeriod('lots', { page: 1, perPage: DEFAULT_LOTS_PER_PAGE }),
        fetchEquipmentPeriod('jobs'),
      ]);

      statusRows.value = Array.isArray(statusPayload?.data) ? statusPayload.data : [];
      lotsRows.value = Array.isArray(lotsPayload?.data) ? lotsPayload.data as Record<string, unknown>[] : [];
      lotsPagination.value = (lotsPayload?.pagination as Pagination) || {
        page: 1,
        per_page: DEFAULT_LOTS_PER_PAGE,
        total: lotsRows.value.length,
        total_pages: 1,
      };
      jobsRows.value = Array.isArray(jobsPayload?.data) ? jobsPayload.data : [];
      queried.timeline = true;
      return true;
    } catch (error) {
      errors.filters = (error as Error)?.message || '查詢時間軸資料失敗';
      return false;
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
    return queryRejects();
  }

  async function setActiveSubTab(tab: unknown, { autoQuery = true }: { autoQuery?: boolean } = {}): Promise<boolean> {
    activeSubTab.value = normalizeSubTab(tab);
    if (!autoQuery) {
      return true;
    }
    return queryActiveSubTab();
  }

  function setSelectedEquipmentIds(ids: unknown[] = []): void {
    selectedEquipmentIds.value = uniqueValues(ids);
  }

  function canExportSubTab(tab: unknown): boolean {
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
    return lotsRows.value.length > 0;
  }

  async function exportSubTab(tab: unknown): Promise<boolean> {
    const normalized = normalizeSubTab(tab);

    if (!canExportSubTab(normalized)) {
      return false;
    }

    exporting[normalized] = true;

    try {
      let exportType = 'equipment_lots';
      const params: Record<string, unknown> = {
        equipment_ids: selectedEquipmentIds.value,
        equipment_names: selectedEquipmentNames.value,
        start_date: startDate.value,
        end_date: endDate.value,
      };

      if (normalized === 'jobs') {
        exportType = 'equipment_jobs';
      } else if (normalized === 'rejects') {
        exportType = 'equipment_rejects';
      }

      await exportCsv({
        exportType,
        params,
      });

      return true;
    } catch (error) {
      const message = (error as Error)?.message || '匯出失敗';
      (errors as Record<string, string>)[normalized] = message;
      return false;
    } finally {
      (exporting as Record<string, boolean>)[normalized] = false;
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
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    queryLots,
    queryJobs,
    queryRejects,
    queryTimeline,
    queryActiveSubTab,
    canExportSubTab,
    exportSubTab,
  };
}
