import { reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../../core/api';
import { exportCsv } from '../utils/csv';
import { normalizeText, parseDateTime, uniqueValues, formatDateTime } from '../utils/values';

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

interface QualityMeta {
  status: string;
  reasons?: string[];
}

interface LotDetailInitial {
  selectedContainerId?: string;
  activeSubTab?: string;
  workcenterGroups?: string[];
}

const LOT_SUB_TABS = Object.freeze([
  'history',
  'materials',
  'rejects',
  'holds',
  'jobs',
]);
const PAGED_SUB_TABS = new Set(['history', 'materials', 'rejects', 'holds']);
const DEFAULT_PER_PAGE = 25;
const PAGE_SIZE_OPTIONS = Object.freeze([25, 50, 100, 200]);

const ASSOCIATION_TABS = new Set(['materials', 'rejects', 'holds', 'jobs']);

const EXPORT_TYPE_MAP = Object.freeze({
  history: 'lot_history',
  materials: 'lot_materials',
  rejects: 'lot_rejects',
  holds: 'lot_holds',
  jobs: 'lot_jobs',
});

function emptyTabFlags() {
  return {
    history: false,
    materials: false,
    rejects: false,
    holds: false,
    jobs: false,
  };
}

function emptyTabErrors() {
  return {
    workcenterGroups: '',
    history: '',
    materials: '',
    rejects: '',
    holds: '',
    jobs: '',
  };
}

function emptyAssociations() {
  return {
    materials: [],
    rejects: [],
    holds: [],
    jobs: [],
  };
}

function emptyPagination(perPage = DEFAULT_PER_PAGE) {
  return {
    page: 1,
    per_page: perPage,
    total: 0,
    total_pages: 1,
  };
}

function emptyPaginationMap() {
  return {
    history: emptyPagination(),
    materials: emptyPagination(),
    rejects: emptyPagination(),
    holds: emptyPagination(),
    jobs: emptyPagination(0),
  };
}

function emptyQualityMetaMap(): Record<string, QualityMeta | null> {
  return {
    history: null,
    materials: null,
    rejects: null,
    holds: null,
    jobs: null,
  };
}

function normalizeSubTab(value: unknown): string {
  const tab = normalizeText(value).toLowerCase();
  return LOT_SUB_TABS.includes(tab) ? tab : 'history';
}

function resolveTimeRangeFromHistory(rows: Record<string, unknown>[]): { time_start: string; time_end: string } | null {
  if (!Array.isArray(rows) || rows.length === 0) {
    return null;
  }

  let minTrackIn: Date | null = null;
  let maxTrackOut: Date | null = null;

  rows.forEach((row) => {
    const trackIn = parseDateTime(row?.TRACKINTIMESTAMP || row?.TRACKINTIME);
    const trackOut = parseDateTime(row?.TRACKOUTTIMESTAMP || row?.TRACKOUTTIME);

    if (trackIn && (!minTrackIn || trackIn < minTrackIn)) {
      minTrackIn = trackIn;
    }

    if (trackOut && (!maxTrackOut || trackOut > maxTrackOut)) {
      maxTrackOut = trackOut;
    }

    if (!maxTrackOut && trackIn) {
      maxTrackOut = trackIn;
    }
  });

  if (!minTrackIn || !maxTrackOut) {
    return null;
  }

  return {
    time_start: formatDateTime(minTrackIn),
    time_end: formatDateTime(maxTrackOut),
  };
}

function resolveEquipmentIdFromHistory(rows: Record<string, unknown>[]): string {
  if (!Array.isArray(rows) || rows.length === 0) {
    return '';
  }

  for (const row of rows) {
    const equipmentId = normalizeText(row?.EQUIPMENTID || row?.RESOURCEID);
    if (equipmentId) {
      return equipmentId;
    }
  }

  return '';
}

export function useLotDetail(initial: LotDetailInitial = {}) {
  ensureMesApiAvailable();

  const selectedContainerId = ref(normalizeText(initial.selectedContainerId));
  const selectedContainerIds = ref(
    initial.selectedContainerId ? [normalizeText(initial.selectedContainerId)] : [],
  );
  const activeSubTab = ref(normalizeSubTab(initial.activeSubTab));

  const workcenterGroups = ref<Record<string, unknown>[]>([]);
  const selectedWorkcenterGroups = ref(uniqueValues(initial.workcenterGroups || []));

  const historyRows = ref<Record<string, unknown>[]>([]);
  const associationRows = reactive(emptyAssociations());
  const pagination = reactive(emptyPaginationMap());
  const qualityMeta = reactive(emptyQualityMetaMap());

  const loading = reactive({
    workcenterGroups: false,
    history: false,
    materials: false,
    rejects: false,
    holds: false,
    jobs: false,
  });

  const loaded = reactive(emptyTabFlags());
  const exporting = reactive(emptyTabFlags());
  const errors = reactive(emptyTabErrors());

  function clearTabData() {
    historyRows.value = [];
    const nextAssociations = emptyAssociations();
    const assocMap = associationRows as Record<string, unknown>;
    Object.keys(nextAssociations).forEach((key) => {
      assocMap[key] = nextAssociations[key as keyof ReturnType<typeof emptyAssociations>];
    });
    const nextPagination = emptyPaginationMap();
    const paginationMap = pagination as Record<string, unknown>;
    const qualityMap = qualityMeta as Record<string, unknown>;
    Object.keys(nextPagination).forEach((key) => {
      paginationMap[key] = nextPagination[key as keyof ReturnType<typeof emptyPaginationMap>];
      qualityMap[key] = null;
    });

    const nextLoaded = emptyTabFlags();
    const loadedMap = loaded as Record<string, unknown>;
    const exportingMap = exporting as Record<string, unknown>;
    const errorsMap = errors as Record<string, unknown>;
    Object.keys(nextLoaded).forEach((key) => {
      loadedMap[key] = nextLoaded[key as keyof ReturnType<typeof emptyTabFlags>];
      exportingMap[key] = false;
      errorsMap[key] = '';
    });
  }

  function getActiveCids() {
    if (selectedContainerIds.value.length > 0) {
      return selectedContainerIds.value;
    }
    const single = selectedContainerId.value;
    return single ? [single] : [];
  }

  async function loadWorkcenterGroups() {
    loading.workcenterGroups = true;
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
      loading.workcenterGroups = false;
    }
  }

  async function loadHistory({ force = false, page = null }: { force?: boolean; page?: number | null } = {}): Promise<boolean> {
    const cids = getActiveCids();
    if (cids.length === 0) {
      return false;
    }

    if (!force && loaded.history) {
      return true;
    }

    loading.history = true;
    errors.history = '';

    try {
      const params = new URLSearchParams();
      // Batch mode: send all CIDs in one request
      if (cids.length > 1) {
        params.set('container_ids', cids.join(','));
      } else {
        params.set('container_id', cids[0]);
      }
      const targetPage = Number(page || pagination.history.page || 1);
      params.set('page', String(targetPage));
      params.set('per_page', String(pagination.history.per_page || DEFAULT_PER_PAGE));
      if (selectedWorkcenterGroups.value.length > 0) {
        params.set('workcenter_groups', selectedWorkcenterGroups.value.join(','));
      }

      const payload = await apiGet(`/api/query-tool/lot-history?${params.toString()}`, {
        timeout: 360000,
        silent: true,
      });

      const inner = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
      historyRows.value = Array.isArray(inner?.data) ? inner.data : [];
      pagination.history = (inner?.pagination as Pagination) || {
        page: targetPage,
        per_page: pagination.history.per_page || DEFAULT_PER_PAGE,
        total: historyRows.value.length,
        total_pages: 1,
      };
      qualityMeta.history = (inner?.quality_meta as QualityMeta) || null;
      loaded.history = true;
      return true;
    } catch (error) {
      errors.history = (error as Error)?.message || '載入 LOT 歷程失敗';
      historyRows.value = [];
      pagination.history = emptyPagination();
      qualityMeta.history = null;
      return false;
    } finally {
      loading.history = false;
    }
  }

  async function loadAssociation(tab: unknown, { force = false, silentError = false, page = null }: { force?: boolean; silentError?: boolean; page?: number | null } = {}): Promise<boolean> {
    const associationType = normalizeSubTab(tab);
    if (!ASSOCIATION_TABS.has(associationType)) {
      return false;
    }

    const cids = getActiveCids();
    if (cids.length === 0) {
      return false;
    }

    const loadedMap = loaded as Record<string, unknown>;
    const loadingMap = loading as Record<string, unknown>;
    const errorsMap = errors as Record<string, unknown>;
    const assocMap = associationRows as Record<string, unknown>;
    const paginationMap = pagination as Record<string, unknown>;
    const qualityMap = qualityMeta as Record<string, unknown>;

    if (!force && loadedMap[associationType]) {
      return true;
    }

    loadingMap[associationType] = true;
    if (!silentError) {
      errorsMap[associationType] = '';
    }

    try {
      if (associationType === 'jobs') {
        // Jobs derive equipment/time from merged history — use first CID as anchor
        if (historyRows.value.length === 0) {
          await loadHistory();
        }

        const equipmentId = resolveEquipmentIdFromHistory(historyRows.value);
        const timeRange = resolveTimeRangeFromHistory(historyRows.value);

        if (!equipmentId || !timeRange?.time_start || !timeRange?.time_end) {
          throw new Error('無法從 LOT 歷程推導 JOB 查詢條件，請先確認歷程資料');
        }

        const params = new URLSearchParams();
        params.set('container_id', cids[0]);
        params.set('type', associationType);
        params.set('equipment_id', equipmentId);
        params.set('time_start', timeRange.time_start);
        params.set('time_end', timeRange.time_end);

        const payload = await apiGet(`/api/query-tool/lot-associations?${params.toString()}`, {
          timeout: 360000,
          silent: true,
        });

        const inner = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
        assocMap[associationType] = Array.isArray(inner?.data) ? inner.data : [];
        paginationMap[associationType] = emptyPagination(0);
        qualityMap[associationType] = null;
      } else {
        // Non-jobs tabs: batch all CIDs into a single request
        const params = new URLSearchParams();
        if (cids.length > 1) {
          params.set('container_ids', cids.join(','));
        } else {
          params.set('container_id', cids[0]);
        }
        params.set('type', associationType);
        const pagRow = paginationMap[associationType] as Pagination;
        const targetPage = Number(page || pagRow?.page || 1);
        if (PAGED_SUB_TABS.has(associationType)) {
          params.set('page', String(targetPage));
          params.set('per_page', String(pagRow?.per_page || DEFAULT_PER_PAGE));
        }

        const payload = await apiGet(`/api/query-tool/lot-associations?${params.toString()}`, {
          timeout: 360000,
          silent: true,
        });

        const inner = (payload as Record<string, unknown>)?.data as Record<string, unknown> || {};
        assocMap[associationType] = Array.isArray(inner?.data) ? inner.data : [];
        if (PAGED_SUB_TABS.has(associationType)) {
          paginationMap[associationType] = inner?.pagination || {
            page: targetPage,
            per_page: pagRow?.per_page || DEFAULT_PER_PAGE,
            total: (assocMap[associationType] as unknown[]).length,
            total_pages: 1,
          };
          qualityMap[associationType] = inner?.quality_meta || null;
        } else {
          paginationMap[associationType] = emptyPagination(0);
          qualityMap[associationType] = null;
        }
      }

      loadedMap[associationType] = true;
      return true;
    } catch (error) {
      assocMap[associationType] = [];
      paginationMap[associationType] = PAGED_SUB_TABS.has(associationType)
        ? emptyPagination()
        : emptyPagination(0);
      qualityMap[associationType] = null;
      if (!silentError) {
        errorsMap[associationType] = (error as Error)?.message || '載入關聯資料失敗';
      }
      return false;
    } finally {
      loadingMap[associationType] = false;
    }
  }

  async function ensureActiveSubTabData() {
    if (activeSubTab.value === 'history') {
      const historyOk = await loadHistory();
      if (historyOk) {
        // History timeline uses hold/material events as marker sources.
        await Promise.allSettled([
          loadAssociation('holds', { silentError: true }),
          loadAssociation('materials', { silentError: true }),
        ]);
      }
      return historyOk;
    }

    return loadAssociation(activeSubTab.value);
  }

  async function setActiveSubTab(tab: unknown): Promise<boolean> {
    activeSubTab.value = normalizeSubTab(tab);
    return ensureActiveSubTabData();
  }

  async function setSelectedContainerId(containerId: unknown): Promise<boolean> {
    const nextId = normalizeText(containerId);
    selectedContainerIds.value = nextId ? [nextId] : [];

    if (nextId === selectedContainerId.value) {
      return ensureActiveSubTabData();
    }

    selectedContainerId.value = nextId;
    clearTabData();

    if (!nextId) {
      return false;
    }

    return ensureActiveSubTabData();
  }

  async function setSelectedContainerIds(cids: unknown[]): Promise<boolean> {
    const normalized = uniqueValues(
      (Array.isArray(cids) ? cids : []).map(normalizeText).filter(Boolean),
    );
    selectedContainerIds.value = normalized;
    selectedContainerId.value = normalized[0] || '';
    clearTabData();

    if (normalized.length === 0) {
      return false;
    }

    return ensureActiveSubTabData();
  }

  async function setSelectedWorkcenterGroups(groups: unknown[]): Promise<boolean> {
    selectedWorkcenterGroups.value = uniqueValues(groups || []);

    if (!selectedContainerId.value) {
      return false;
    }

    loaded.history = false;
    return loadHistory({ force: true });
  }

  async function setSubTabPage(tab: unknown, nextPage: unknown): Promise<boolean> {
    const normalized = normalizeSubTab(tab);
    if (!PAGED_SUB_TABS.has(normalized)) {
      return false;
    }
    const pageNumber = Number(nextPage || 1);
    if (normalized === 'history') {
      return loadHistory({ force: true, page: pageNumber });
    }
    return loadAssociation(normalized, { force: true, page: pageNumber });
  }

  async function setSubTabPerPage(tab: unknown, perPage: unknown): Promise<boolean> {
    const normalized = normalizeSubTab(tab);
    if (!PAGED_SUB_TABS.has(normalized)) {
      return false;
    }
    (pagination as Record<string, Pagination>)[normalized].per_page = Number(perPage) || DEFAULT_PER_PAGE;
    if (normalized === 'history') {
      return loadHistory({ force: true, page: 1 });
    }
    return loadAssociation(normalized, { force: true, page: 1 });
  }

  function getRowsByTab(tab: unknown): Record<string, unknown>[] {
    const normalized = normalizeSubTab(tab);
    if (normalized === 'history') {
      return historyRows.value;
    }
    if (!ASSOCIATION_TABS.has(normalized)) {
      return [];
    }
    return (associationRows as Record<string, Record<string, unknown>[]>)[normalized] || [];
  }

  async function exportSubTab(tab: unknown): Promise<boolean> {
    const normalized = normalizeSubTab(tab);
    const exportType = (EXPORT_TYPE_MAP as Record<string, string>)[normalized];
    const cids = getActiveCids();
    const exportingMap = exporting as Record<string, unknown>;
    const errorsMap = errors as Record<string, unknown>;

    if (!exportType || cids.length === 0) {
      return false;
    }

    exportingMap[normalized] = true;
    errorsMap[normalized] = '';

    try {
      const params: Record<string, unknown> = {
        container_ids: cids,
      };

      if (normalized === 'jobs') {
        if (historyRows.value.length === 0) {
          await loadHistory();
        }
        const equipmentId = resolveEquipmentIdFromHistory(historyRows.value);
        const timeRange = resolveTimeRangeFromHistory(historyRows.value);
        if (!equipmentId || !timeRange?.time_start || !timeRange?.time_end) {
          throw new Error('無法取得 JOB 匯出所需條件');
        }
        params.equipment_id = equipmentId;
        params.time_start = timeRange.time_start;
        params.time_end = timeRange.time_end;
      }

      await exportCsv({
        exportType,
        params,
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
    lotSubTabs: LOT_SUB_TABS,
    selectedContainerId,
    selectedContainerIds,
    activeSubTab,
    workcenterGroups,
    selectedWorkcenterGroups,
    historyRows,
    associationRows,
    pagination,
    qualityMeta,
    loading,
    loaded,
    exporting,
    errors,
    loadWorkcenterGroups,
    loadHistory,
    loadAssociation,
    ensureActiveSubTabData,
    setActiveSubTab,
    setSelectedContainerId,
    setSelectedContainerIds,
    setSelectedWorkcenterGroups,
    pageSizeOptions: PAGE_SIZE_OPTIONS,
    setSubTabPage,
    setSubTabPerPage,
    getRowsByTab,
    exportSubTab,
    clearTabData,
  };
}
